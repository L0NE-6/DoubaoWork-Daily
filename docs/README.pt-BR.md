<div align="center">

<sub><strong>L0NE-6 · DAILY SIGNAL</strong></sub>

# Doubao Work Daily

**Script de arquivo único para o check-in diário do Doubao Work: encontra a campanha, recebe a recompensa e confirma o resultado relendo os detalhes da campanha.**

[简体中文](../README.md) | [English](README.en.md) | [繁體中文](README.zh-Hant.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Português (BR)](README.pt-BR.md)

<img src="https://img.shields.io/github/v/release/L0NE-6/DoubaoWork-Daily?style=for-the-badge&label=Release&color=2ea44f&logo=github" />
<img src="https://img.shields.io/github/stars/L0NE-6/DoubaoWork-Daily?style=for-the-badge&label=Stars&color=FFC75F&logo=github" />
<img src="https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white" />

</div>

> A documentação completa em chinês está em [../README.md](../README.md).

## ✨ Recursos principais

- Chama `/alice/user/launch` para identificar o grupo de campanha ativo.
- Escolhe o endpoint v3 de detalhes ou a lista regular de campanhas.
- Continua apenas quando existe exatamente uma tarefa `daily_checkin`.
- Trata recompensa já recebida, campanha não publicada e condição não atendida como estados neutros.
- Envia um evento best-effort `landing/report` imediatamente antes do check-in real.
- Relê os detalhes após o resgate e aceita somente `checked_in_today=true`; `task_status=3` nunca substitui um false explícito.
- Suporta várias contas, modo somente consulta, seleção de uma conta e notificações PushPlus, Bark e WeCom.

> A máquina de estados segue `doubaowork/checkin`, `checkin_state` e `rewards` do Agent2Providers `v3.4.2`. Este projeto é uma implementação clean-room do mesmo protocolo Cookie + campaign + reward. Comece com `--query`.

## 🚀 Configuração mínima

```bash
python -m pip install -r requirements.txt
```

Entre em `https://www.doubao.com/chat/`, abra F12 → Network e copie o Cookie completo de uma requisição. Ele precisa conter `sessionid` ou `sessionid_ss`.

Conta única:

```text
DOUBAOWORK_COOKIE=sessionid=...; sessionid_ss=...
```

Várias contas:

```text
DOUBAOWORK_COOKIES=
Principal|sessionid=...; sessionid_ss=...
Secundária|sessionid=...; sessionid_ss=...
```

Execução:

```bash
python doubaowork_daily.py --query
python doubaowork_daily.py
python doubaowork_daily.py --only 1
python doubaowork_daily.py --no-notify
```

## 🐧 Qinglong

```bash
pip3 install requests
```

Defina `DOUBAOWORK_COOKIES` no painel e crie:

```text
15 9 * * * python3 doubaowork_daily.py
```

Execute `--query` manualmente antes de ativar o agendamento.

## ☁️ GitHub Actions

O workflow está em [../.github/workflows/daily.yml](../.github/workflows/daily.yml). A execução manual está ativa e o bloco de agendamento está comentado.

| Secret | Obrigatório | Uso |
| :--- | :---: | :--- |
| `DOUBAOWORK_COOKIES` | Um dos dois | Cookies de várias contas |
| `DOUBAOWORK_COOKIE` | Um dos dois | Cookie de uma conta |
| `DOUBAOWORK_DEVICE_ID` | Opcional | Device ID |
| `DOUBAOWORK_WEB_ID` | Opcional | Web ID |
| `DOUBAOWORK_FINGERPRINT` | Opcional | Fingerprint |
| `DOUBAOWORK_PROXY` | Opcional | Proxy |
| `PUSHPLUS_TOKEN` / `BARK_URL` / `WECOM_WEBHOOK` | Opcional | Notificações |

Para ativar o agendamento, remova os comentários. `15 1 * * *` usa UTC e corresponde a 09:15 em Pequim.

## 🔧 Variáveis principais

| Variável | Descrição |
| :--- | :--- |
| `DOUBAOWORK_COOKIES` | Várias contas: `nome\|cookie` |
| `DOUBAOWORK_COOKIE` | Cookie de uma conta |
| `DOUBAOWORK_ACCOUNTS_FILE` | Arquivo JSON de contas |
| `DOUBAOWORK_DEVICE_ID` | Device ID opcional |
| `DOUBAOWORK_WEB_ID` | Web ID opcional |
| `DOUBAOWORK_FINGERPRINT` | Fingerprint opcional |
| `DOUBAOWORK_USER_AGENT` | User-Agent opcional |
| `DOUBAOWORK_CLIENT_VERSION` | Versão do cliente; padrão `2.33.5` |
| `DOUBAOWORK_PROXY` | Proxy HTTP(S) / SOCKS5 |
| `DOUBAOWORK_NO_NOTIFY` | `1` desativa notificações |

## 📊 Critério de sucesso

A resposta do endpoint de resgate não basta. Depois de solicitar a recompensa, o script relê os detalhes e aceita somente `checked_in_today=true`. Um valor `task_status=3` não substitui um false explícito. Tarefas pendentes ficam em um ledger substituído atomicamente e protegido por um arquivo de bloqueio fixo para threads e processos.

## 🔒 Privacidade

- Um Cookie é uma credencial de login.
- Guarde-o apenas em variáveis de ambiente, GitHub Secrets ou shell local temporário.
- Não publique cookies em issues, README, releases ou chats.
- Os logs mascaram o Cookie e o projeto nunca grava o Cookie em texto puro; apenas um ledger pending mínimo e com hash é persistido.
- Se um Cookie foi exposto, renove a sessão.

## Limites de uso e redistribuição

O repositório oficial, os scripts, as instruções de implantação e os downloads das Releases são gratuitos. Não são permitidos empacotamento pago, implantação paga, exigência de assinatura, revenda, remoção de autoria, personificação do autor, uso da identidade ou dos QR codes do autor como endosso, nem repostagem em contas, grupos ou canais sem relação para desviar tráfego. O conteúdo irregular pode ser retirado; o autor pode pausar atualizações, arquivar ou excluir o repositório. Consulte [../NOTICE.md](../NOTICE.md) para as regras completas.

## 🔗 Links

- [Releases](https://github.com/L0NE-6/DoubaoWork-Daily/releases)
- [Issues](https://github.com/L0NE-6/DoubaoWork-Daily/issues)
- [Changelog](../CHANGELOG.md)
- [License](../LICENSE)
