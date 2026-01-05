# 🐙 GitHub 新手入門指南 - 零成本掛機篇

這份指南將教你如何將這個專案上傳到 GitHub，並啟動我們剛剛設定好的「免費自動掛機」功能。

---

## 第一步：準備工作

1.  **註冊 GitHub 帳號**
    *   前往 [github.com](https://github.com/) 註冊一個免費帳號。

2.  **安裝 Git 工具**
    *   (如果你還沒安裝) 下載 [Git for Windows](https://git-scm.com/download/win)。
    *   安裝過程中一路狂按 "Next" 到底即可。

---

## 第二步：建立雲端倉庫 (Repository)

1.  登入 GitHub。
2.  點擊右上角的 **+** 號，選擇 **"New repository"**。
3.  **Repository name**: 輸入 `chain-monitor` (或你喜歡的名字)。
4.  **Visibility**: 選擇 **Public** (公開) 或 **Private** (私有)。
    *   *建議選 Private，保護你的 Discord Webhook 不外洩。但 Private 倉庫的 Actions 免費額度有限制 (每月 2000 分鐘，通常夠用)。*
5.  點擊 **"Create repository"**。

---

## 第三步：上傳代碼 (本地操作)

回到你的電腦，在你存放代碼的資料夾 (`c:\Users\huseven\Desktop\公鏈分析`) 中：

1.  **右鍵點擊空白處**，選擇 **"Open Git Bash Here"** (或在終端機進入此目錄)。
2.  依序輸入以下指令 (一行一行複製貼上)：

```bash
# 1. 初始化 Git
git init

# 2. 將所有檔案加入暫存區
git add .

# 3. 提交第一次版本
git commit -m "🚀 Initial commit: 全鏈監控系統 v2.0"

# 4.設定主分支名稱
git branch -M main

# 5. 連接到 GitHub (請將下面的網址換成你在第二步建立的倉庫網址!!)
# 例如: git remote add origin https://github.com/你的帳號/chain-monitor.git
git remote add origin <你的GitHub倉庫網址>

# 6. 推送代碼上去
git push -u origin main
```
*(注意：第一次推送時會跳出視窗要求你登入 GitHub，輸入帳密授權即可)*

---

## 第四步：設定自動掛機 (GitHub Actions)

代碼上傳成功後，GitHub 就會自動偵測到我們寫好的腳本 (`.github/workflows/daily_monitor.yml`)。

**最後一個關鍵步驟：設定 Discord 通知**

1.  回到你的 GitHub 倉庫網頁。
2.  點擊上方的 **Settings (設定)** 頁籤。
3.  在左側選單找到 **Secrets and variables** -> 點擊 **Actions**。
4.  點擊綠色的 **New repository secret** 按鈕。
5.  輸入資訊：
    *   **Name**: `DISCORD_WEBHOOK`
    *   **Secret**: (貼上你的 Discord Webhook 網址)
6.  點擊 **Add secret**。

---

## 🎉 完成！

現在，你的系統已經在雲端啟動了！
*   它會每 **30 分鐘** 自動醒來工作一次。
*   你可以點擊倉庫上方的 **Actions** 頁籤來查看它的運作狀態。
*   每次運行完，它會把更新後的資料庫 (`chain_data.db`) 和 HTML 報告自動傳回你的倉庫。

**享受完全免費的 24H 監控吧！🚀**
