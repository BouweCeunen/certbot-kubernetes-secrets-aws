
def get_domains_hosted_zone(hosted_zones, domain):
    domains = domain.split('.')
    hosted_zone = None
    for zone in hosted_zones:
        parsed_zone = zone.split('.')
        parsed_domain = domain.split('.')
        while len(parsed_domain) >= 1 and len(parsed_zone) >= 1:
            if parsed_domain[-1] != parsed_zone[-1]:
                break
            parsed_domain.pop(-1)
            parsed_zone.pop(-1)
        if len(parsed_zone) == 0 and len(parsed_domain) <= len(domains):
            domains = parsed_domain
            hosted_zone = zone
    return (hosted_zone, domains)

domain = 'alertmanager.k8s.bouweceunen.com'
hosted_zones = ['bouweceunen.be', 'bouweceunen.com', 'waiterassist.be', 'cryptogathering.be', 'athumn.be', 'waiterassist.com', 'cryptogathering.com', 'athumn.com', 'k8s.bouweceunen.com', 'athumn.app', 'cryptogathering.app', 'waiterassist.app', 'lol.k8s.bouweceunen.com', 'api.cryptogathering.com', 'api.cryptogathering.be', 'api.cryptogathering.app', 'api.waiterassist.com', 'api.waiterassist.be', 'api.waiterassist.app']
print(get_domains_hosted_zone(hosted_zones, domain))