
import requests
import json
import time

def get_top_protocols(chain_name):
    print(f"🔍 Fetching protocols for chain: {chain_name}...")
    try:
        # DefiLlama protocols endpoint
        url = "https://api.llama.fi/protocols"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        # Filter for the specific chain
        # Note: DefiLlama uses specific formatting for chains, usually capitalized or specific slugs
        # We need to handle case sensitivity. "Ethereum", "Solana", "Binance" (for BSC)
        
        target_chain = chain_name.title()
        if target_chain == 'Bsc': target_chain = 'Binance'
        
        chain_protocols = []
        for p in data:
            # Check if chain is in the protocol's chains list
            if target_chain in p.get('chains', []) or p.get('chain') == target_chain:
                # We only want significant protocols, say TVL > 1M
                if p.get('tvl', 0) > 1_000_000:
                    chain_protocols.append({
                        'name': p['name'],
                        'symbol': p['symbol'],
                        'tvl': p['tvl'],
                        'change_1d': p.get('change_1d', 0),
                        'category': p.get('category', 'Unknown')
                    })
        
        # Sort by 1-day change to find "Hot" protocols, or TVL for "Safe" ones
        # Let's find "Movers" - highest 24h growth
        chain_protocols.sort(key=lambda x: x['change_1d'] or -100, reverse=True)
        
        return chain_protocols[:5]
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

# Test with a few chains
chains_to_test = ['Solana', 'Ethereum', 'Base', 'Bsc', 'Arbitrum']

for c in chains_to_test:
    top = get_top_protocols(c)
    print(f"\n🏆 Top Movers on {c}:")
    for p in top:
        print(f"   - {p['name']} ({p['symbol']}): +{p['change_1d']:.2f}% (TVL: ${p['tvl']/1e6:.1f}M) [{p['category']}]")
    print("-" * 30)
