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

_client = None
_region_cache = {}


def _parse_cpu_mem(cpu_str: str, mem_str: str):
    def parse_val(s):
        m = re.match(r"(\d+)", s)
        return int(m.group(1)) if m else 0
    cpu = parse_val(cpu_str)
    mem_val = parse_val(mem_str)
    if "21" in mem_str and "102" not in mem_str:
        if mem_val >= 1024:
            mem_gb = mem_val // 1024
        else:
            mem_gb = mem_val / 1024
    else:
        mem_gb = mem_val
    return cpu, mem_gb


async def _get_client():
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30, follow_redirects=True)
    return _client


async def _load_products(region_id: str):
    if region_id in _region_cache:
        return
    client = await _get_client()
    url = "https://portal.huaweicloud.com/api/calculator/rest/cbc/portalcalculatornodeservice/v4/api/productInfo"
    params = {"urlPath": "ecs", "tag": "general.online.portal", "region": region_id, "tab": "calc", "sign": "common"}
    try:
        resp = await client.get(url, headers=HEADERS, params=params)
        data = resp.json()
        products = data.get("product", {}).get("ec2_vm", [])
        region_specs = []
        for p in products:
            code = p.get("resourceSpecCode", "")
            if "linux" not in code:
                continue
            cpu_str = p.get("cpu", "")
            mem_str = p.get("mem", "")
            cpu, mem = _parse_cpu_mem(cpu_str, mem_str)
            plan_list = p.get("planList", [])
            monthly = [pl for pl in plan_list if pl.get("billingMode") == "MONTHLY"]
            price = monthly[0].get("amount", 0) if monthly else 0
            pid = monthly[0].get("productId", "") if monthly else ""
            if cpu > 0 and mem > 0 and price > 0:
                region_specs.append({"cpu": cpu, "mem": mem, "code": code, "price": float(price), "productId": pid})
        _region_cache[region_id] = region_specs
    except Exception:
        logger.exception("Failed to fetch Huawei products for region %s", region_id)
        _region_cache[region_id] = []


def _group_cheapest(specs: list) -> dict:
    groups = {}
    for s in specs:
        key = (s["cpu"], s["mem"])
        if key not in groups or s["price"] < groups[key]["price"]:
            groups[key] = s
    return groups


async def get_instance_types(region_id: str = "cn-north-4") -> list:
    await _load_products(region_id)
    specs = _region_cache.get(region_id, [])
    groups = _group_cheapest(specs)
    return [{"cpu": s["cpu"], "mem": s["mem"], "instance_type": s["code"]} for s in groups.values()]


async def query_all_prices(region_id: str):
    await _load_products(region_id)
    specs = _region_cache.get(region_id, [])
    groups = _group_cheapest(specs)
    return [{"provider": "华为云", "instance_type": s["code"], "cpu": s["cpu"], "mem": s["mem"],
             "monthly_price": round(s["price"], 2), "currency": "CNY"} for s in groups.values()]


async def query_price(region_id: str, cpu: int, mem: int):
    await _load_products(region_id)
    specs = _region_cache.get(region_id, [])
    matching = [s for s in specs if s["cpu"] == cpu and s["mem"] == mem]
    if not matching:
        return {"provider": "华为云", "error": f"该地域无 {cpu}核{mem}G 的实例规格"}
    cheapest = min(matching, key=lambda x: x["price"])
    return {"provider": "华为云", "instance_type": cheapest["code"],
            "monthly_price": round(cheapest["price"], 2), "currency": "CNY"}
