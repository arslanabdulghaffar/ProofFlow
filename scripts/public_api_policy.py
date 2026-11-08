"""Exact public API variant of the existing networkless API container policy."""

import copy

from install_product_services import validate_container

PUBLIC_MOUNTS = {
    "/run/proofflow-product-api": ("/run/proofflow-public-api", True),
    "/etc/proofflow-product/tls": ("/etc/proofflow-public-api/tls", False),
}


def validate_public_container(config, image_env):
    normalized = copy.deepcopy(config)
    try:
        if config["Config"]["Labels"].get("proofflow.role") != "product-public-api":
            raise ValueError
        normalized["Config"]["Labels"]["proofflow.role"] = "product-api"
        changed = set()
        for mount in normalized["Mounts"]:
            destination = mount["Destination"]
            if destination in PUBLIC_MOUNTS:
                if (mount["Source"], mount["RW"]) != PUBLIC_MOUNTS[destination]:
                    raise ValueError
                changed.add(destination)
                mount["Source"] = {"/run/proofflow-product-api": "/run/proofflow-product-api",
                    "/etc/proofflow-product/tls": "/etc/proofflow-product-api/tls"}[destination]
        if changed != set(PUBLIC_MOUNTS):
            raise ValueError
        validate_container(normalized, "api", image_env)
    except (KeyError, TypeError, ValueError):
        raise RuntimeError("PUBLIC_CONTAINER_CONFIGURATION_CHANGED") from None
