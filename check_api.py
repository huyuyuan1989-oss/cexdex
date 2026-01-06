import aiohttp
import asyncio
import time

async def check():
    url = "https://api.llama.fi/protocol/binance-cex"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            
            if 'tokensInUsd' not in data:
                print("No tokensInUsd")
                return

            history = data['tokensInUsd']
            print(f"Total records: {len(history)}")
            if not history:
                return
                
            last = history[-1]
            first = history[0]
            print(f"Latest: {last['date']} ({time.ctime(last['date'])})")
            print(f"Oldest: {first['date']} ({time.ctime(first['date'])})")
            
            # Check gaps
            current_ts = last['date']
            target_w1 = current_ts - 7*86400
            
            # Find closest to W1
            closest = None
            min_diff = 1e9
            for r in history:
                diff = abs(r['date'] - target_w1)
                if diff < min_diff:
                    min_diff = diff
                    closest = r
            
            print(f"Target W1: {target_w1}")
            print(f"Closest match diff: {min_diff/3600:.2f} hours")
            print(f"Match Date: {closest['date']} ({time.ctime(closest['date'])})")

asyncio.run(check())
