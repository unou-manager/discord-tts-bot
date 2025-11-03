# Discord 読み上げボット

VOICEVOXを使用したDiscord読み上げボットです。

## 機能

- テキストメッセージを自動的に音声で読み上げ
- メッセージキュー機能（複数のメッセージを順番に再生）
- 150文字制限（超過分は「以下略」と読み上げ）
- 話者の変更機能
- スキップ・キューのクリア機能

## セットアップ

### 0. Discord Developer Portal
事前の管理画面での作成手順は省略。
参考：
https://qiita.com/1ntegrale9/items/cb285053f2fa5d0cccdf

注意点：
権限設定（最小推奨権限設定）
 ```bash
 View Channels
 Read Messages
 Send Messages
 Connect
 Speak
 Use Slash Commands
```

またdocker構築についても省略

### 1. 環境変数の設定

`.env`ファイルを作成:

```bash
cp .env.example .env
```

`.env`ファイルを編集してDiscordボットトークンを設定:

```env
DISCORD_TOKEN=あなたのボットトークン
```

### 2. Dockerで起動

```bash
docker-compose up -d
```

### 3. ログの確認

```bash
docker-compose logs -f discord-bot
```

## コマンド

- `/join` - ボイスチャンネルに参加
- `/leave` - ボイスチャンネルから退出
- `/setvoice speaker:数字` - 話者を変更（例: `/setvoice speaker:3`）
- `/skip` - 現在再生中の音声をスキップ
- `/clear` - 音声キューをクリア

## 使い方

1. ボイスチャンネルに参加
2. `/join` コマンドでボットを呼ぶ
3. テキストチャンネルにメッセージを送信すると自動的に読み上げられます
4. 複数のメッセージを送信すると、キューに追加されて順番に再生されます

## トラブルシューティング

### ボットが起動しない

```bash
docker-compose logs discord-bot
```

### VOICEVOXエンジンが起動しない

```bash
docker-compose logs voicevox
```

### コンテナの再起動

```bash
docker-compose restart
```

### コンテナの停止

```bash
docker-compose down
```
