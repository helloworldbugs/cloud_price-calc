import httpx
import re
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Referer": "https://www.huaweicloud.com/pricing/calculator.html",
    "Origin": "https://www.huaweicloud.com",
    "Accept": "application/json, text/plain, */*",
}

_SIZE_TO_VCPU = {
    "large": 2, "xlarge": 4,
    "2xlarge": 8, "4xlarge": 16, "8xlarge": 32,
    "16xlarge": 64, "32xlarge": 128, "64xlarge": 256,
}

_client = None
_region_cache = {}

API_URL = "https://portal.huaweicloud.com/api/calculator/rest/cbc/portalcalculatornodeservice/v4/api/productInfo"


def _parse_cpu_mem(resource_spec_code: str, cpu_raw, mem_raw):
    code_lower = resource_spec_code.lower() if resource_spec_code else ""

    cpu = 0
    if isinstance(cpu_raw, (int, float)):
        cpu = int(cpu_raw)
    elif isinstance(cpu_raw, str) and cpu_raw.isdigit():
        cpu = int(cpu_raw)

    mem_gb = 0
    if isinstance(mem_raw, (int, float)):
        mem_gb = int(mem_raw)
    elif isinstance(mem_raw, str) and mem_raw.isdigit():
        mem_gb = int(mem_raw)

    if cpu == 0 or mem_gb == 0:
        parts = code_lower.split(".")
        if len(parts) >= 3:
            size = parts[2] if "rds" not in code_lower else parts[2] if len(parts) > 2 else ""
            if not size and len(parts) >= 4:
                size = parts[3]

            try:
                cpu = _SIZE_TO_VCPU.get(size, 0)
                if cpu == 0:
                    m = re.match(r"(\d+)xlarge", size)
                    if m:
                        cpu = int(m.group(1)) * 4
            except Exception:
                cpu = 0

        if cpu > 0 and mem_gb == 0 and len(parts) >= 3:
            try:
                mem_key = parts[3] if len(parts) > 3 else parts[2]
                ratio_match = re.search(r"(\d+)", mem_key)
                if ratio_match:
                    ratio = int(ratio_match.group(1))
                    mem_gb = cpu * ratio
            except Exception:
                pass

    return cpu, int(mem_gb) if mem_gb else 0


async def _get_client():
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30, follow_redirects=True)
    return _client


async def _load_products(region_id: str):
    if region_id in _region_cache:
        return
    client = await _get_client()
    params = {"urlPath": "rdsformariadb", "tag": "general.online.portal", "region": region_id, "tab": "calc", "sign": "common"}
    try:
        resp = await client.get(API_URL, headers=HEADERS, params=params)
        data = resp.json()
        products = data.get("product", {})

        vm_products = products.get("rdsformariadb_rdsformariadb.vm", [])
        region_specs = []
        for p in vm_products:
            code = p.get("resourceSpecCode", "")
            instance_type = p.get("DB Instance Type", "")
            cpu_raw = p.get("CPU", "")
            mem_raw = p.get("Memory", "")
            cpu, mem = _parse_cpu_mem(code, cpu_raw, mem_raw)

            if cpu <= 0 or mem <= 0:
                continue

            plan_list = p.get("planList", [])
            monthly = [pl for pl in plan_list if pl.get("billingMode") == "MONTHLY"]
            ondemand = [pl for pl in plan_list if pl.get("billingMode") == "ONDEMAND"]
            is_ondemand = False
            hourly_price = 0
            if monthly:
                price = float(monthly[0].get("amount", 0))
                pid = monthly[0].get("productId", "")
            elif ondemand:
                hourly = float(ondemand[0].get("amount", 0))
                hourly_price = round(hourly, 4)
                price = round(hourly * 730, 2)
                pid = ondemand[0].get("productId", "")
                is_ondemand = True
            else:
                continue

            if price <= 0:
                continue

            region_specs.append({
                "cpu": cpu, "mem": mem, "code": code,
                "instance_type": instance_type,
                "price": price, "productId": pid,
                "is_ondemand": is_ondemand,
                "hourly_price": hourly_price,
            })

        _region_cache[region_id] = region_specs
    except Exception:
        logger.exception("Failed to fetch Huawei RDS products for region %s", region_id)
        _region_cache[region_id] = []


def _group_cheapest(specs: list, prefer_single_node: bool = True):
    groups = {}
    for s in specs:
        key = (s["cpu"], s["mem"], s.get("instance_type", ""))
        if key not in groups or s["price"] < groups[key]["price"]:
            groups[key] = s
    return groups


async def get_instance_types(region_id: str = "cn-north-4") -> list:
    await _load_products(region_id)
    specs = _region_cache.get(region_id, [])
    seen = set()
    result = []
    for s in specs:
        key = (s["cpu"], s["mem"])
        if key not in seen:
            seen.add(key)
            result.append({"cpu": s["cpu"], "mem": s["mem"], "instance_type": s["code"]})
    return result


async def query_all_prices(region_id: str):
    await _load_products(region_id)
    specs = _region_cache.get(region_id, [])
    results = []

    single_node = [s for s in specs if s.get("instance_type") == "单机"]
    ha_node = [s for s in specs if s.get("instance_type") == "主备"]

    preferred = single_node if single_node else ha_node

    cheapest_per_spec = {}
    for s in specs:
        key = (s["cpu"], s["mem"])
        if key not in cheapest_per_spec or s["price"] < cheapest_per_spec[key]["price"]:
            cheapest_per_spec[key] = s

    for s in cheapest_per_spec.values():
        item = {
            "provider": "华为云",
            "instance_type": s["code"],
            "cpu": s["cpu"],
            "mem": s["mem"],
            "monthly_price": round(s["price"], 2),
            "currency": "CNY",
            "db_instance_type": s.get("instance_type", ""),
        }
        if s.get("is_ondemand"):
            item["is_ondemand"] = True
            item["hourly_price"] = s["hourly_price"]
        if s.get("instance_type") != "单机":
            item["note"] = "最低双节点"
        results.append(item)
    return results


async def query_price(region_id: str, cpu: int, mem: int):
    await _load_products(region_id)
    specs = _region_cache.get(region_id, [])

    single_node = [s for s in specs if s["cpu"] == cpu and s["mem"] == mem and s.get("instance_type") == "单机"]
    if single_node:
        cheapest = min(single_node, key=lambda x: x["price"])
    else:
        matching = [s for s in specs if s["cpu"] == cpu and s["mem"] == mem]
        if not matching:
            return {"provider": "华为云", "error": f"该地域无 {cpu}核{mem}G 的RDS规格"}
        cheapest = min(matching, key=lambda x: x["price"])

    result = {
        "provider": "华为云",
        "instance_type": cheapest["code"],
        "monthly_price": round(cheapest["price"], 2),
        "currency": "CNY",
        "cpu": cpu, "mem": mem,
        "db_instance_type": cheapest.get("instance_type", ""),
    }
    if cheapest.get("is_ondemand"):
        result["is_ondemand"] = True
        result["hourly_price"] = cheapest["hourly_price"]
    if cheapest.get("instance_type") != "单机":
        result["note"] = "最低双节点"
    return result
