# key_ticket_system
Secure HLS System

## Build and Install (Almalinux 10)
### Fast API
```
$ sudo dnf -y update
$ sudo dnf -y groupinstall "Development Tools"
$ sudo dnf -y install policycoreutils-python-utils bzip2-devel.x86_64 ncurses-devel.x86_64 libffi-devel.x86_64 readline-devel.x86_64 sqlite-devel.x86_64

$ git clone https://github.com/pyenv/pyenv.git ~/.pyenv
$ echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
$ echo '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
$ echo 'eval "$(pyenv init - bash)"' >> ~/.bashrc

$ echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bash_profile
$ echo '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bash_profile
$ echo 'eval "$(pyenv init - bash)"' >> ~/.bash_profile

$ source .bashrc

$ pyenv install 3.13.7
$ pyenv global 3.13.7

$ git clone https://github.com/takashi74/key_ticket_system
$ ln -s key_ticket_system pyconjp
$ cd pyconjp

$ sudo cp infra/pyconjp-ticket.service /etc/systemd/system/

$ python -m venv .venv
$ source .venv/bin/activate
(.venv) $ pip install -U pip
(.venv) $ pip install -r requirements.txt
(.venv) $ cp app/.env.sample app/.env
(.venv) $ vi app/.env
(.venv) $ deactivate

# (selinux todo)

$ sudo systemctl daemon-reload
$ sudo systemctl enable pyconjp-ticket.service
$ sudo systemctl start pyconjp-ticket.service
```

## Sequence Diagram
### Live Stream Playing
```mermaid
sequenceDiagram
    actor U as User
    participant A as Cloudflare Pages<br>2025.pycon.jp
    participant B as Pretix SSO<br>pretix.eu/pyconjp
    participant D as Auth Server<br>nginx/gunicorn/uvicorn<br>python/FastAPI
    participant C as Pretix API<br>pretix.eu/pyconjp
    participant I as J-Stream Cloud<br>Live
    participant J as J-Stream Cloud<br>HLS-Auth
    actor P as PyCon JP Staff

    par 事前準備
        P->>B: SSOアプリを作成
        Note over P,B: /control/organizer/pyconjp/ssoclients
        B->>P: client_id, client_secret
        P->>C: APIを作成
        Note over P,C: /control/organizer/pyconjp/teams
        C->>P: API Token
        P->>A: client_idをページに反映
        P->>D: client_secret, apitokenを.envに反映
        P->>I: ライブイベントの作成
        I-->>P: ライブ情報の取得
        P->>J: コンテンツID(ユニークID)、ストリームIDの発行
        J-->>P: ストリームID
        P->>P: ユーザー情報を作成(ユニークID)
        P->>J: 再生させるユーザーの登録
        P->>I: ライブ配信を実施
    end
    U->>A: ライブ視聴ページにアクセス
    A->>+B: ユーザーログイン情報を取得
    Note over A,B: /pyconjp/oauth2/v1/authorize
    alt Pretixにログインしていない
    B->>U: ログインページを表示
    U->>B: ログイン
    else Pretixにログインしている
    B-->>D: code
    Note over B,D: /callback
    D->>B: アクセストークンを取得
    Note over B,D: /pyconjp/oauth2/v1/token
    B-->>D: Access Token
    D->>B: ユーザー情報を取得
    Note over B,D: /pyconjp/oauth2/v1/userinfo<br>Authorization: Bearer
    B-->>D: json { userinfo }
    D->>C: メールアドレスを元に購入情報を取得
    Note over C,D: /api/v1/organizers/pyconjp/orders/?email={E-mail}<br>Authorization: Token
    C-->>D: json { Orders Data }
    D->>D: Encode JWT
    D->>A: JWT付きで視聴ページにリダイレクト
    end
    opt リロード時など
    U->>A: 再生ボタンの押下
    end
    A->>D: JWTの整合性を確認
    Note over A,D: /verify
    opt 購入していない場合 整合性が不正な場合
    D->>A: 購入を促すメッセージを表示
    end
    D->>J: 再生権限情報を登録
    J->>D: session_id
    D->>A: 再生用アドレスを取得
    A-->>A: プレイヤーを表示
    A->>U: プレイヤーを再生
    J-->>U: 動画の視聴
```