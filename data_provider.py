"""
🔗 DataProvider - 全鏈數據獲取模組 v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
功能特色：
- 集中管理所有 API 端點 (DefiLlama, Stablecoins 等)
- 帶重試機制的 fetch_with_retry 方法 (支援 HTTP 429 指數退避)
- 純數據獲取，不含處理邏輯

Usage:
    from data_provider import DataProvider
    
    async def main():
        provider = DataProvider()
        async with provider:
            protocols = await provider.get_protocols()
            chain_tvl = await provider.get_chain_tvl('ethereum')
"""

import asyncio
import aiohttp
import logging
from typing import Optional, Dict, Any, List

# 設定日誌
logger = logging.getLogger(__name__)


class DataProvider:
    """
    集中化的 API 數據獲取器
    
    特點：
    - 單一 Session 管理
    - HTTP 429 (Rate Limit) 指數退避處理
    - 支援 Retry-After header
    - 所有 API 端點集中管理
    """
    
    # ================= API 端點設定 =================
    DEFILLAMA_BASE = "https://api.llama.fi"
    STABLECOINS_BASE = "https://stablecoins.llama.fi"
    BINANCE_FUTURES_BASE = "https://fapi.binance.com"
    BYBIT_BASE = "https://api.bybit.com"
    FEAR_GREED_BASE = "https://api.alternative.me"
    
    ENDPOINTS = {
        # DefiLlama 核心 API
        'protocols': '/protocols',                          # 所有協議列表
        'protocol_detail': '/protocol/{slug}',              # 單一協議詳情
        'chains': '/v2/chains',                             # 所有公鏈列表
        'chain_tvl': '/v2/historicalChainTvl/{chain}',      # 公鏈歷史 TVL
        
        # 穩定幣 API
        'stablecoins': '/stablecoins?includePrices=true',   # 穩定幣供應量
        
        # Binance 期貨 API
        'funding_rates': '/fapi/v1/premiumIndex',           # 資金費率
    }
    
    # 預設請求 Headers (模擬瀏覽器避免被攔截)
    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }
    
    def __init__(self, timeout: int = 30):
        """
        初始化 DataProvider
        
        Args:
            timeout: 請求超時時間 (秒)
        """
        self._session: Optional[aiohttp.ClientSession] = None
        self._timeout = aiohttp.ClientTimeout(total=timeout)
    
    async def __aenter__(self):
        """Context manager 入口 - 建立 Session"""
        self._session = aiohttp.ClientSession(
            timeout=self._timeout,
            headers=self.DEFAULT_HEADERS
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager 出口 - 關閉 Session"""
        if self._session:
            await self._session.close()
            self._session = None
    
    @property
    def session(self) -> aiohttp.ClientSession:
        """取得 HTTP Session (確保已初始化)"""
        if self._session is None:
            raise RuntimeError("DataProvider 需要使用 'async with' context manager")
        return self._session
    
    # ================= 核心方法：帶重試的 Fetch =================
    
    async def fetch_with_retry(
        self, 
        url: str, 
        params: Optional[Dict] = None, 
        retries: int = 3,
        base_delay: float = 2.0
    ) -> Optional[Any]:
        """
        帶重試機制的非同步請求
        
        支援：
        - HTTP 429 (Rate Limit) 指數退避
        - Retry-After header 自動處理
        - 5xx 伺服器錯誤重試
        - 連線超時重試
        
        Args:
            url: 請求 URL
            params: 可選的查詢參數
            retries: 最大重試次數
            base_delay: 基礎等待時間 (秒)
        
        Returns:
            JSON 回應資料，失敗時返回 None
        """
        for attempt in range(retries):
            try:
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    
                    elif response.status == 429:  # Rate Limited
                        # 優先使用 Retry-After header
                        retry_after = response.headers.get('Retry-After')
                        if retry_after:
                            try:
                                wait_time = int(retry_after)
                            except ValueError:
                                wait_time = base_delay * (2 ** attempt)
                        else:
                            # 指數退避: 2^attempt * base_delay
                            wait_time = base_delay * (2 ** attempt)
                        
                        # 最長等待 60 秒
                        wait_time = min(wait_time, 60)
                        logger.warning(f"⏳ API 限速 (429)，等待 {wait_time} 秒... [{url[-50:]}]")
                        await asyncio.sleep(wait_time)
                        continue  # 重試
                    
                    elif response.status >= 500:
                        # 伺服器錯誤，等待後重試
                        wait_time = base_delay * (attempt + 1)
                        logger.warning(f"⚠️ 伺服器錯誤 {response.status}，等待 {wait_time} 秒後重試...")
                        await asyncio.sleep(wait_time)
                        continue
                    
                    else:
                        # 其他狀態碼 (4xx 等) - 記錄但不重試
                        logger.warning(f"⚠️ API 回應 {response.status}: {url[-80:]}")
                        return None
                        
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ 請求超時 (嘗試 {attempt + 1}/{retries}): {url[-80:]}")
            except aiohttp.ClientError as e:
                logger.error(f"❌ 網路請求失敗: {type(e).__name__}: {e}")
            except Exception as e:
                logger.error(f"❌ 未預期的錯誤: {type(e).__name__}: {e}")
            
            # 等待後進行下一次重試
            if attempt < retries - 1:
                await asyncio.sleep(base_delay)
        
        logger.error(f"❌ 請求失敗 (已重試 {retries} 次): {url[-80:]}")
        return None
    
    # ================= DefiLlama API 方法 =================
    
    async def get_protocols(self) -> Optional[List[Dict]]:
        """
        獲取所有協議列表
        
        Returns:
            協議列表 (包含 TVL, change_1d, change_7d 等資訊)
        """
        url = f"{self.DEFILLAMA_BASE}{self.ENDPOINTS['protocols']}"
        return await self.fetch_with_retry(url)
    
    async def get_protocol_detail(self, slug: str) -> Optional[Dict]:
        """
        獲取單一協議的詳細資訊
        
        Args:
            slug: 協議 slug (例如 'binance-cex', 'uniswap')
        
        Returns:
            協議詳情 (包含 tokensInUsd 歷史紀錄等)
        """
        endpoint = self.ENDPOINTS['protocol_detail'].format(slug=slug)
        url = f"{self.DEFILLAMA_BASE}{endpoint}"
        return await self.fetch_with_retry(url)
    
    async def get_chains(self) -> Optional[List[Dict]]:
        """
        獲取所有公鏈列表
        
        Returns:
            公鏈列表 (包含 TVL 等基本資訊)
        """
        url = f"{self.DEFILLAMA_BASE}{self.ENDPOINTS['chains']}"
        return await self.fetch_with_retry(url)
    
    async def get_chain_tvl(self, chain_name: str) -> Optional[List[Dict]]:
        """
        獲取單一公鏈的歷史 TVL 數據
        
        Args:
            chain_name: 公鏈名稱 (例如 'ethereum', 'bsc', 'solana')
        
        Returns:
            歷史 TVL 列表 [{date, tvl}, ...]
        """
        endpoint = self.ENDPOINTS['chain_tvl'].format(chain=chain_name)
        url = f"{self.DEFILLAMA_BASE}{endpoint}"
        return await self.fetch_with_retry(url)
    
    # ================= 穩定幣 API 方法 =================
    
    async def get_stablecoins(self) -> Optional[Dict]:
        """
        獲取穩定幣流通量數據
        
        Returns:
            穩定幣數據 (包含 peggedAssets 列表)
        """
        url = f"{self.STABLECOINS_BASE}{self.ENDPOINTS['stablecoins']}"
        return await self.fetch_with_retry(url)
    
    # ================= Binance API 方法 =================
    
    # ================= 輔助方法 =================
    
    async def get_top_protocols_on_chain(self, chain_name: str, limit: int = 3) -> List[Dict]:
        """
        [V4 Feature] 獲取特定鏈上表現最好的協議
        
        Args:
            chain_name: 公鏈名稱 (e.g., 'solana', 'base')
            limit: 返回數量
            
        Returns:
            協議列表 [{name, symbol, change_1d, category, tvl}]
        """
        # 1. 獲取所有協議 (如果尚未緩存)
        if not hasattr(self, '_protocols_cache') or not self._protocols_cache:
            self._protocols_cache = await self.get_protocols()
            
        if not self._protocols_cache:
            return []
            
        # 2. 鏈名稱標準化 (DefiLlama 使用 Title Case，如 'Ethereum', 'Base')
        target_chain = chain_name.title()
        if target_chain.lower() == 'bsc': target_chain = 'Binance'
        
        # 3. 過濾與排序
        chain_protocols = []
        for p in self._protocols_cache:
            # 檢查鏈歸屬 (p['chain'] 是主鏈, p['chains'] 是所有部署鏈)
            is_on_chain = (p.get('chain') == target_chain) or (target_chain in p.get('chains', []))
            
            if is_on_chain and p.get('tvl', 0) > 1_000_000: # 過濾 TVL > 1M 的協議
                chain_protocols.append({
                    'name': p.get('name'),
                    'symbol': p.get('symbol'),
                    'change_1d': p.get('change_1d') or 0,
                    'tvl': p.get('tvl', 0),
                    'category': p.get('category', 'Unknown')
                })
        
        # 4. 排序：優先找 "爆發中" 的項目 (24H 漲幅高)
        # 過濾掉異常數據 (> 10000% 或 < -90%)
        chain_protocols = [p for p in chain_protocols if -90 < p['change_1d'] < 10000]
        chain_protocols.sort(key=lambda x: x['change_1d'], reverse=True)
        
        return chain_protocols[:limit]

    # ================= Binance API 方法 =================
    
    async def get_funding_rates(self) -> Optional[List[Dict]]:
        """
        獲取 Binance 期貨資金費率
        
        Returns:
            資金費率列表 [{symbol, lastFundingRate, ...}, ...]
        """
        try:
            url = f"{self.BINANCE_FUTURES_BASE}{self.ENDPOINTS['funding_rates']}"
            return await self.fetch_with_retry(url)
        except Exception:
            # Fallback logic here if needed, or rely on fetch_with_retry's robust handling
            return None
    
    # ================= 便捷方法 =================
    
    async def get_cex_protocols(self, min_tvl: float = 100_000_000) -> List[Dict]:
        """
        獲取中心化交易所 (CEX) 協議列表
        
        Args:
            min_tvl: 最小 TVL 過濾 (預設 $100M)
        
        Returns:
            CEX 列表，按 TVL 降序排列
        """
        protocols = await self.get_protocols()
        if not protocols:
            return []
        
        cex_list = []
        for p in protocols:
            if p.get('category') == 'CEX':
                tvl = p.get('tvl', 0) or 0
                if tvl >= min_tvl:
                    cex_list.append({
                        'name': p['name'],
                        'symbol': p.get('symbol', ''),
                        'slug': p.get('slug', ''),
                        'tvl': tvl,
                        'change_1d': p.get('change_1d', 0) or 0,
                        'change_7d': p.get('change_7d', 0) or 0,
                        'logo': p.get('logo', ''),
                    })
        
        # 按 TVL 降序排列
        cex_list.sort(key=lambda x: x['tvl'], reverse=True)
        return cex_list
    
    # ================= 驗證測試 =================
    
    async def get_funding_rates(self) -> Dict[str, float]:
        """
        獲取主要幣種的資金費率 (Fallback: Binance -> Bybit)
        """
        rates = {'BTC': 0.0, 'ETH': 0.0}
        
        # 1. Try Binance
        try:
            url = f"{self.BINANCE_FUTURES_BASE}{self.ENDPOINTS['funding_rates']}"
            data = await self.fetch_with_retry(url)
            if data and isinstance(data, list):
                for item in data:
                    s = item.get('symbol')
                    if s == 'BTCUSDT': rates['BTC'] = float(item.get('lastFundingRate', 0))
                    elif s == 'ETHUSDT': rates['ETH'] = float(item.get('lastFundingRate', 0))
                if rates['BTC'] != 0: return rates
        except Exception as e:
            logger.debug(f"Binance Funding Rate failed, trying Bybit... ({e})")

        # 2. Try Bybit (Fallback)
        try:
            for symbol in ['BTCUSDT', 'ETHUSDT']:
                url = f"{self.BYBIT_BASE}/v5/market/tickers?category=linear&symbol={symbol}"
                data = await self.fetch_with_retry(url)
                if data and data.get('retCode') == 0:
                    item = data['result']['list'][0]
                    key = 'BTC' if 'BTC' in symbol else 'ETH'
                    rates[key] = float(item.get('fundingRate', 0))
            if rates['BTC'] != 0: return rates
        except Exception as e:
            logger.debug(f"Bybit Funding Rate failed, trying OKX... ({e})")

        # 3. Try OKX (Fallback 2)
        try:
            # OKX: BTC-USDT-SWAP, ETH-USDT-SWAP
            # https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP
            for coin in ['BTC', 'ETH']:
                url = f"https://www.okx.com/api/v5/public/funding-rate?instId={coin}-USDT-SWAP"
                data = await self.fetch_with_retry(url)
                if data and data.get('code') == '0':
                    rates[coin] = float(data['data'][0].get('fundingRate', 0))
            return rates
        except Exception as e:
            logger.error(f"All Funding Rate sources failed: {e}")
            return rates

    async def get_open_interest(self, symbol: str) -> float:
        """
        獲取合約未平倉量 (Fallback: Binance -> Bybit -> OKX)
        """
        # 1. Try Binance
        try:
            endpoint = "/fapi/v1/openInterest"
            url = f"{self.BINANCE_FUTURES_BASE}{endpoint}"
            data = await self.fetch_with_retry(url, params={'symbol': symbol})
            if data: return float(data.get('openInterest', 0))
        except Exception as e:
            logger.debug(f"Binance OI failed for {symbol}, trying Bybit... ({e})")
            
        # 2. Try Bybit (Fallback)
        try:
            url = f"{self.BYBIT_BASE}/v5/market/open-interest?category=linear&symbol={symbol}&intervalTime=5min&limit=1"
            data = await self.fetch_with_retry(url)
            if data and data.get('retCode') == 0 and data['result']['list']:
                return float(data['result']['list'][0].get('openInterest', 0))
        except Exception as e:
            logger.debug(f"Bybit OI failed for {symbol}, trying OKX... ({e})")
            
        # 3. Try OKX (Fallback 2)
        try:
            # Symbol mapping: BTCUSDT -> BTC-USDT-SWAP
            okx_symbol = symbol.replace('USDT', '-USDT-SWAP')
            url = f"https://www.okx.com/api/v5/public/open-interest?instId={okx_symbol}"
            data = await self.fetch_with_retry(url)
            if data and data.get('code') == '0':
                # OKX returns OI in Contracts (usually 1 BTC or 0.01 BTC? No, SWAP is 1 contract = 0.01 BTC or similar?)
                # Wait, OKX linear swap contract value is usually 1 BTC? No, often 0.01 or 0.001.
                # Actually OKX returns `oi` (in contracts) and `oiCcy` (in coins).
                # We need COINS. `oiCcy` is "Open interest in currency".
                return float(data['data'][0].get('oiCcy', 0))
        except Exception as e:
            logger.error(f"All OI sources failed for {symbol}: {e}")
            
                # 4. Try Gate.io (Fallback 3)
        try:
            # Gate.io: BTC_USDT
            gate_symbol = symbol.replace('USDT', '_USDT') # BTC_USDT
            url = f"https://api.gateio.ws/api/v4/futures/usdt/tickers?contract={gate_symbol}"
            data = await self.fetch_with_retry(url)
            if data and isinstance(data, list) and len(data) > 0:
                # Gate returns 'total_size' in Base Currency (BTC)
                return float(data[0].get('total_size', 0))
        except Exception as e:
            logger.debug(f"Gate.io OI failed for {symbol}: {e}")
            
        return 0.0


    async def get_derivatives_data(self) -> Dict[str, Any]:
        """
        一次性獲取所有衍生品數據 (OI + Funding)
        """
        # 需要導入 datetime
        from datetime import datetime 
        
        funding = await self.get_funding_rates()
        btc_oi = await self.get_open_interest('BTCUSDT')
        eth_oi = await self.get_open_interest('ETHUSDT')
        
        return {
            'funding_rates': funding,
            'open_interest': {
                'BTC': btc_oi,
                'ETH': eth_oi
            },
            'timestamp': datetime.utcnow().isoformat() + "Z"
        }

    async def fetch_fear_greed_index(self) -> Dict[str, Any]:
        """
        獲取加密貨幣貪婪恐慌指數
        Returns: {'value': 50, 'value_classification': 'Neutral'}
        """
        try:
            url = f"{self.FEAR_GREED_BASE}/fng/"
            data = await self.fetch_with_retry(url)
            
            if data and data.get('data'):
                latest = data['data'][0]
                return {
                    'value': int(latest.get('value', 50)),
                    'value_classification': latest.get('value_classification', 'Neutral'),
                    'timestamp': latest.get('timestamp')
                }
            return {'value': 50, 'value_classification': 'Neutral'}
        except Exception as e:
            logger.error(f"Error fetching Fear & Greed Index: {e}")
            return {'value': 50, 'value_classification': 'Neutral'}

    async def test(self) -> bool:
        """
        執行驗證測試，確認 API 可正常獲取數據
        
        Returns:
            True 如果所有測試通過
        """
        print("=" * 60)
        print("🧪 DataProvider 驗證測試")
        print("=" * 60)
        
        all_passed = True
        
        # 測試 1: 獲取協議列表
        print("\n[1/3] 測試獲取協議列表...")
        protocols = await self.get_protocols()
        if protocols and len(protocols) > 0:
            print(f"   ✅ 成功！共獲取 {len(protocols)} 個協議")
        else:
            print("   ❌ 失敗：無法獲取協議列表")
            all_passed = False
        
        # 測試 2: 獲取 Ethereum 歷史 TVL
        print("\n[2/3] 測試獲取 Ethereum 歷史 TVL...")
        eth_tvl = await self.get_chain_tvl('ethereum')
        if eth_tvl and len(eth_tvl) > 0:
            latest = eth_tvl[-1]
            print(f"   ✅ 成功！共 {len(eth_tvl)} 筆記錄")
            print(f"      最新 TVL: ${latest.get('tvl', 0) / 1e9:.2f}B")
        else:
            print("   ❌ 失敗：無法獲取 ETH TVL 數據")
            all_passed = False
        
        # 測試 3: 獲取 CEX 列表
        print("\n[3/3] 測試獲取 CEX 列表...")
        cex_list = await self.get_cex_protocols()
        if cex_list and len(cex_list) > 0:
            print(f"   ✅ 成功！共 {len(cex_list)} 個 CEX (TVL >= $100M)")
            print(f"      Top 3: {', '.join([c['name'] for c in cex_list[:3]])}")
        else:
            print("   ❌ 失敗：無法獲取 CEX 列表")
            all_passed = False
        
        print("\n" + "=" * 60)
        if all_passed:
            print("🎉 所有測試通過！DataProvider 運作正常。")
        else:
            print("⚠️ 部分測試失敗，請檢查網路連線或 API 狀態。")
        print("=" * 60)
        
        return all_passed


# ================= 主程式入口 (獨立執行時) =================

async def main():
    """獨立執行時的測試入口"""
    # 設定基本 logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    async with DataProvider() as provider:
        await provider.test()


if __name__ == '__main__':
    asyncio.run(main())
