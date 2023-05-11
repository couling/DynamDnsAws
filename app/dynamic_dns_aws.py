import importlib.metadata
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Generator, Iterable, List, Union

import boto3
import click
import dns.exception
import dns.resolver
import yaml
from dns.rdatatype import RdataType

_log = logging.getLogger(__name__)


@click.command()
@click.option("--config", default="/etc/dynamic-dns-aws/dynamic-dns.yaml",
              type=click.Path(file_okay=True, dir_okay=False,exists=True,path_type=Path))
@click.option("--version", is_flag=True)
def main(config: Path, version: bool):
    if version:
        print(f"dynamic-dns-aws {importlib.metadata.version('dynamic-dns-aws')}")
        return

    logging.basicConfig(format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s", level=logging.DEBUG)

    _log.info("Starting up")

    with open(config, "r") as file:
        config = yaml.safe_load(file)

    for unit, level in config.get('log_levels').items():
        logging.getLogger(unit).level = logging.getLevelName(level)

    _log.debug("Configuration \n%s", config)
    _log.info("Monitoring for %s", ", ".join(all_names(config['zones'])))

    ip_finder = IPFinder(servers=config['servers'], domain=config['domain'])
    updater = IPUpdater(zones=config['zones'], ttl=rationalise_time(config['ttl']))

    sleep_time = rationalise_time(config['interval'])

    try:
        while True:
            _log.debug("Updating")
            try:
                my_ip = sorted(ip_finder.find_my_ip())
                _log.debug("My IPs %s", my_ip)
                updater.update_ipv4(my_ip)
            except dns.exception.DNSException:
                _log.error("Could not find my IP", exc_info=True)
            time.sleep(sleep_time)
    finally:
        _log.info("Shutting down")


def all_names(zones: Dict[str, List[str]]):
    for zone, names in zones.items():
        for name in names:
            yield f"{name}.{zone}"


def rationalise_time(t: Union[int, float, dict]) -> int:
    if isinstance(t, dict):
        t = timedelta(**t).total_seconds()
    return int(t)


class IPUpdater:
    def __init__(self, zones: Dict[str,List[str]], ttl: int):
        self._zones = zones
        self._ttl = ttl
        self._client = boto3.client("route53")

    def update_ipv4(self, address: List[str]):
        address_spec = [{"Value": a} for a in address]
        address_spec.sort()
        for zone, names in self._zones.items():
            zone_id = self._get_zone_id(zone)
            to_update = {f"{name}.{zone}." for name in names} if isinstance(names, list) else {names}
            for record in self._list_zone_records(zone_id):
                if record['Type'] == 'A' and record['Name'] in to_update:
                    if record['ResourceRecords'] == address_spec and record['TTL'] == self._ttl:
                        _log.debug("%s still good", record['Name'])
                        to_update.remove(record['Name'])
                        if not to_update:
                            break
                    else:
                        _log.info(f"Old record found for %s: %s TTL: %s",
                                  record['Name'], record['ResourceRecords'], record['TTL'])
            if to_update:
                if to_update:
                    _log.info("Updating %s names %s to %s", zone, to_update, address)
                    self._update_records(zone_id=zone_id, names=to_update, addresses=address_spec)

    def _update_records(self, zone_id: str, names: Iterable[str], addresses: List[Dict[str, str]]):
        changes = []
        for name in names:
            changes.append({
                'Action': 'UPSERT',
                'ResourceRecordSet': {
                    'Name': name,
                    'Type': 'A',
                    'TTL': self._ttl,
                    'ResourceRecords': addresses
                }
            })
        _log.debug("Changes %s", changes)
        self._client.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={'Changes': changes}
        )

    def _get_zone_id(self, zone_name: str):
        result = self._client.list_hosted_zones_by_name(DNSName=zone_name)
        return next(iter(result['HostedZones']))['Id']

    def _list_zone_records(self, zone_id: str) -> Generator[Dict, None, None]:
        results = self._client.list_resource_record_sets(HostedZoneId=zone_id)
        yield from results['ResourceRecordSets']
        while results['IsTruncated']:
            results = self._client.list_resource_record_sets(
                HostedZoneId=zone_id,
                StartRecordName=results['NextRecordName'],
                StartRecordType=results['NextRecordType']
            )
            yield from results['ResourceRecordSets']


class IPFinder:
    _dns_servers: List[str]
    _refresh_dns_server_time = time.time()

    def __init__(self, servers: List[str], domain: str):
        self._servers = servers
        self._domain = domain
        self._resolver = dns.resolver.Resolver()
        self._refresh_dns_server_time = time.time()

    def find_my_ip(self) -> List[str]:
        self._refresh_dns_servers()
        result = self._resolver.resolve(self._domain)
        return list(record.address for record in result if result.rdtype is RdataType.A)

    def _refresh_dns_servers(self):
        if self._refresh_dns_server_time <= time.time():
            _log.debug("Refreshing DNS server")

            self._resolver.nameservers.clear()
            expiration = []
            exceptions = []
            for server in self._servers:
                try:
                    result = dns.resolver.resolve(server, rdtype=RdataType.A)
                except dns.exception.DNSException as ex:
                    _log.warning("Could not resolve %s due to %s", server, str(ex))
                    exceptions.append(ex)
                else:
                    expiration.append(result.expiration)
                    for record in result:
                        if record.rdtype is RdataType.A:
                            self._resolver.nameservers.append(record.address)

            if not self._resolver.nameservers:
                raise exceptions[-1]

            self._refresh_dns_server_time = min(expiration)
            _log.debug("IP check using DNS servers %s until %s",
                       self._resolver.nameservers,
                       datetime.fromtimestamp(self._refresh_dns_server_time).replace(microsecond=0))


if __name__ == '__main__':
    main()
