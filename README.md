# Dynamic DNS AWS

This is a very simple project for creating a dynmaic DNS agent that directly updates AWS Route 53

# How to Setup

## Configuration file

The configuration file needs to be named: `/etc/dnamic-dns-aws/dynamic-dns.yaml`

In docker this can either be a bind-mount or added to the image.  The critic

```yaml
zones:
  # Edit these!
  # The keys (example.com) are the name of the AWS hosted zone
  # The values are the entries and may be either hostnames or FQDNs.
  foo.example.com:
    - bar.example.com
    - baz

ttl: {minutes: 5}

domain: myip.opendns.com

interval: {minutes: 5}

servers:
  - resolver1.opendns.com
  - resolver2.opendns.com
  - resolver3.opendns.com
  - resolver4.opendns.com

log_levels:
  null: INFO
  botocore: INFO
  urllib3: INFO
```

## Docker compose

```yaml
version: "3.4"

services:

  dynamic_dns:
    image: couling/dynamic-dns-aws:latest
    restart: always
    volumes:
      # Bind mount your configuration
      - ./dynamic-dns.yaml:/etc/dnamic-dns-aws/dynamic-dns.yaml
      # If not running in AWS cloud, then bind mount credentials
      - /root/.aws/:/root/.aws
```