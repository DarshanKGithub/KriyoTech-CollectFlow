"""Fixed KriyoPay identity; reseller instance modes have been retired."""
def platform_capable():
    return True


def product_name():
    return "KriyoPay"


def export_prefix():
    return "kriyopay"
