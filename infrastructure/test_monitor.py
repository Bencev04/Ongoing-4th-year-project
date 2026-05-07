"""Quick test script for monitor data fetching."""
import asyncio
import traceback
from monitor.aws import fetch_environment
from monitor.k8s import fetch_k8s_for_env

async def test():
    try:
        r = await fetch_environment("staging", None, "eu-west-1")
        print("AWS fetch OK")
        for k, v in r.items():
            status = v.get("status", "?") if isinstance(v, dict) else str(v)[:50]
            print(f"  {k}: {status}")
    except Exception as e:
        print(f"AWS fetch FAILED: {e}")
        traceback.print_exc()

    try:
        r = await fetch_k8s_for_env("staging", None, "eu-west-1")
        print(f"K8s fetch OK: {r.get('status')}")
    except Exception as e:
        print(f"K8s fetch FAILED: {e}")
        traceback.print_exc()

asyncio.run(test())
