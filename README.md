# Consulta Dte

> Projeto de portfólio de **Victória Pedrosa** (Automação, Processos e Dados). Automação desenvolvida para um escritório de contabilidade; **esta é uma versão com dados fictícios** — nomes, CNPJs, e-mails e IDs internos foram substituídos.

## Problema de negócio
Mensagens do DTE (domicílio tributário eletrônico) precisam ser verificadas periodicamente para cada empresa.

## Antes x depois
| | Antes | Depois |
|---|---|---|
| Como é feito | Acesso manual ao DTE, empresa a empresa. | Robô consulta o DTE e salva os PDFs em pastas por data. |

## Ganho
- Nenhuma notificação fiscal perdida.

## Tecnologias
OCR de captcha, Python, SQLite, Selenium, pandas

## Arquivos
- `automacao_dte.py`
- `requirements.txt`

## Como rodar
1. `pip install -r requirements.txt`
2. Copie `.env.exemplo` para `.env` e preencha os caminhos.
3. Execute o script principal.

## Autora
Victória Pedrosa — Product Owner do Time de IA, automação de processos contábeis e fiscais.
