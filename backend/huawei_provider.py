import httpx
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Referer": "https://www.huaweicloud.com/pricing/calculator.html",
    "Origin": "https://www.huaweicloud.com",
    "Accept": "application/json, text/plain, */*",
}

_client = None
_product_cache = {}
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


async def _load_products(region_id: str = "cn-north-4"):
    if region_id in _region_cache:
        return
    client = await _get_client()
    url = "https://portal.huaweicloud.com/api/calculator/rest/cbc/portalcalculatornodeservice/v4/api/productInfo"
    params = {
        "urlPath": "ecs",
        "tag": "general.online.portal",
        "region": region_id,
        "tab": "calc",
        "sign": "common",
    }
    try:
        resp = await client.get(url, headers=HEADERS, params=params)
        data = resp.json()
        products = data.get("product", {}).get("ec2_vm", [])
        region_specs = {}
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
            if cpu > 0 and mem > 0:
                region_specs[(cpu, mem)] = {"code": code, "price": float(price), "productId": pid}
        _region_cache[region_id] = region_specs
    except:
        _region_cache[region_id] = {}


def _find_instance_type(cpu: int, mem: int, region_id: str = "cn-north-4"):
    specs = _region_cache.get(region_id, {})
    if (cpu, mem) in specs:
        return specs[(cpu, mem)]
    return None


async def get_instance_types(region_id: str = "cn-north-4") -> list:
    await _load_products(region_id)
    specs = _region_cache.get(region_id, {})
    seen = set()
    result = []
    for (cpu, mem), info in specs.items():
        key = (cpu, mem)
        if key not in seen:
            seen.add(key)
            result.append({"cpu": cpu, "mem": mem, "instance_type": info["code"]})
    return sorted(result, key=lambda x: (x["cpu"], x["mem"]))


async def query_all_prices(region_id: str, disk_size: int = 40, bandwidth: int = 0):
    await _load_products(region_id)
    specs = _region_cache.get(region_id, {})
    results = []
    for (cpu, mem), info in specs.items():
        price = info.get("price", 0)
        if price > 0:
            results.append({"provider": "华为云", "instance_type": info["code"],
                            "cpu": cpu, "mem": mem, "monthly_price": round(float(price), 2), "currency": "CNY"})
    return results


async def query_price(region_id: str, cpu: int, mem: int, disk_size: int = 40, bandwidth: int = 0):
    await _load_products(region_id)
    spec = _find_instance_type(cpu, mem, region_id)
    if not spec:
        return {"provider": "华为云", "error": f"该地域无 {cpu}核{mem}G 的实例规格"}

    code = spec.get("code", "")
    base_price = spec.get("price", 0)

    if base_price > 0:
        return {
            "provider": "华为云",
            "instance_type": code,
            "monthly_price": round(float(base_price), 2),
            "currency": "CNY",
        }

    return {
        "provider": "华为云",
        "error": f"未找到匹配的实例规格 {cpu}C{mem}G",
        "instance_type": code,
    }
