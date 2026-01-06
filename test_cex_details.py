
import asyncio
import aiohttp
import json

async def fetch_cex_details():
    async with aiohttp.ClientSession() as session:
        # 獲取 Binance 的 protocol slug
        binance_slug = "binance-cex"
        
        detail_url = f"https://api.llama.fi/protocol/{binance_slug}"
        async with session.get(detail_url) as detail_resp:
            detail_data = await detail_resp.json()
            
            if 'tokensInUsd' in detail_data:
                print("\nTokensInUsd 數據範例 (最新一筆):")
                # 取得最後一筆 (最新數據)
                latest = detail_data['tokensInUsd'][-1]
                print(f"Date: {latest['date']}")
                print(json.dumps(latest['tokens'], indent=2)[:500])
                
                # 計算穩定幣佔比
                tokens = latest['tokens']
                stablecoins = ['USDT', 'USDC', 'DAI', 'BUSD', 'USDD', 'TUSD', 'FDUSD']
                total_usd = sum(tokens.values())
                stable_usd = sum(v for k, v in tokens.items() if k in stablecoins)
                
                print(f"\n總資產: ${total_usd:,.2f}")
                print(f"穩定幣資產: ${stable_usd:,.2f} ({stable_usd/total_usd*100:.2f}%)")
                print(f"非穩定幣: ${total_usd-stable_usd:,.2f} ({(total_usd-stable_usd)/total_usd*100:.2f}%)")

if __name__ == "__main__":
    asyncio.run(fetch_cex_details())
