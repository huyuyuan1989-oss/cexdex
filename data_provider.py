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
    
    async def get_funding_rates(self) -> Optional[List[Dict]]:
        """
        獲取 Binance 期貨資金費率
        
        Returns:
            資金費率列表 [{symbol, lastFundingRate, ...}, ...]
        """
        url = f"{self.BINANCE_FUTURES_BASE}{self.ENDPOINTS['funding_rates']}"
        return await self.fetch_with_retry(url)
    
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
        獲取主要幣種的資金費率 (Funding Rate)
        Returns: {'BTC': 0.0001, 'ETH': 0.0001}
        """
        try:
            url = f"{self.BINANCE_FUTURES_BASE}{self.ENDPOINTS['funding_rates']}"
            data = await self.fetch_with_retry(url)
            
            rates = {}
            if data:
                for item in data:
                    symbol = item.get('symbol', '')
                    if symbol == 'BTCUSDT':
                        rates['BTC'] = float(item.get('lastFundingRate', 0))
                    elif symbol == 'ETHUSDT':
                        rates['ETH'] = float(item.get('lastFundingRate', 0))
            
            return rates
        except Exception as e:
            logger.error(f"Error fetching funding rates: {e}")
            return {'BTC': 0.0, 'ETH': 0.0}

    async def get_open_interest(self, symbol: str) -> float:
        """
        獲取合約未平倉量 (Open Interest) - 單位: 幣的數量 (Coins)
        Args:
            symbol: 'BTCUSDT' or 'ETHUSDT'
        Returns:
            OI value (Quantity of coins)
        """
        try:
            endpoint = "/fapi/v1/openInterest"
            url = f"{self.BINANCE_FUTURES_BASE}{endpoint}"
            data = await self.fetch_with_retry(url, params={'symbol': symbol})
            
            return float(data.get('openInterest', 0)) if data else 0.0
        except Exception as e:
            logger.error(f"Error fetching OI for {symbol}: {e}")
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
