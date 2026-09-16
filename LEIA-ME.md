# SoulFork Find

**https://find.soulfork.com.br** — prospecção de clientes por nicho e localização. O Find
busca empresas no Google Maps, visita o site de cada uma, extrai **WhatsApp, e-mail,
telefone, Instagram, TikTok, Facebook e LinkedIn**, valida o **CNPJ** na base pública da
Receita, faz o **diagnóstico técnico** do site (HTTPS, celular, Pixel, GTM, LGPD,
formulário) e entrega um **score de oportunidade 0–100** com o motivo da primeira conversa.

É um site, não um programa instalável.

## Publicação (VPS com Easypanel)

1. **Easypanel → projeto → + Service → App**, fonte **GitHub** (`EdnoBraga/soulfork-radar`,
   branch `main`), build **Dockerfile**.
2. **Environment:** `FIND_SENHA`, `FIND_SECRET_KEY` (ambas com 12+ caracteres; a chave
   pode ser `python -c "import secrets; print(secrets.token_hex(32))"`) e
   `GOOGLE_PLACES_API_KEY`. Sem as duas primeiras o app **não sobe** — de propósito.
3. **Mounts:** volume em `/data` (banco de leads, exportações, token da Meta).
   Sem volume, cada novo deploy apaga os leads.
4. **Domains:** `find.soulfork.com.br`, porta **8000**, HTTPS ligado.
5. **DNS** (onde o domínio soulfork.com.br é administrado): registro **A** `find` →
   IP da VPS. O certificado sai sozinho quando o DNS propagar.
6. Confira: `https://find.soulfork.com.br/saude` responde `ok`, e a home pede senha.

O contêiner roda **1 processo** com 8 threads: as buscas em andamento vivem na memória
dele. Não aumente o número de réplicas sem antes mover a fila para o banco.

## Rodar na própria máquina (desenvolvimento)

Precisa de Python 3.10+.

```bash
pip install -r requirements.txt
python -m prospector.web
```

Sem `FIND_SENHA` o app abre sem login — só serve para uso local.

### Chave do Google Places (obrigatória para buscar)

1. Acesse [console.cloud.google.com](https://console.cloud.google.com) e crie um projeto
2. Menu → **APIs e serviços** → **Biblioteca** → ative **Places API (New)**
3. Ative o faturamento (o Google dá crédito mensal gratuito; uma busca de 20 empresas
   custa centavos de dólar)
4. **Credenciais** → **Criar credenciais** → **Chave de API**
5. Em restrições da chave, restrinja à *Places API (New)*. **Não** use restrição por
   referer HTTP (a chamada sai do servidor, não do navegador)
6. No servidor, cadastre como variável de ambiente (ou pela tela Configuração). Local: copie `.env.example` para `.env`:

```
GOOGLE_PLACES_API_KEY=AIza...
```

## Usar

### Interface (recomendado)

```bash
python -m prospector.web
```

Abre `http://localhost:8760` no navegador. Fluxo: **Buscar** (nicho + estado + cidade +
quantas) → **Leads** (tabela com oportunidade, nota, contato, ranking e canais, filtros
que não gastam crédito) → **Análises** (por onde começar, quem subiu e caiu no Maps,
por que o topo ganha, o mercado da busca) → **CSV / Excel / PDF**.

- **Nicho completo:** escolha um nome do grupo "Nicho completo" no menu (ex.: `odontologia`)
  e o Find combina as variações de nome do `nichos.json` até chegar à quantidade pedida.
  Um termo avulso (`pizzaria`) busca só ele. O Google entrega até 60 empresas por termo.
- **Custo:** a busca para de pedir páginas assim que junta a quantidade; a tela de leads
  mostra quantas chamadas ao Google foram feitas.
- **Andamento:** cada lead tem Não abordado → Contatado → Respondeu → Reunião → Proposta →
  Ganho / Perdido / Descartado, com filtro na tela da busca e em "Todos os leads".
- **Buscas salvas:** reabrem depois de reiniciar o servidor (ficam no banco).
- **Por que essa nota?** Cada lead mostra os pontos que somaram, com a evidência.

### Linha de comando

```bash
python -m prospector nichos                                      # nichos prontos
python -m prospector buscar fisioterapia --local "Brasília, DF"  # rodada completa
python -m prospector analisar https://exemplo.com.br             # 1 site, sem gastar API
python -m prospector lista --exportar                            # tudo que já foi coletado
```

## O que cada score significa

| Faixa | Score | Leitura |
|---|---|---|
| Oportunidade quente | 65+ | dor grande E canal claro de abordagem |
| Vale abordar | 45–64 | dor real, abordagem possível |
| Talvez | 25–44 | pouca dor ou pouco canal |
| Pouco a oferecer | <25 | presença razoável ou sem por onde abordar |

O score combina **dor** (o que está quebrado que a SoulFork resolve) e **viabilidade**
(canais de contato + sinais de que o negócio está vivo). Empresa fechada, CNPJ baixado
ou sem nenhum canal público é descartada.

## Regras de honestidade embutidas (não remova)

- **GA4 nunca é afirmado como ausente** — não é verificável pelo HTML servido. GTM e
  Meta Pixel são (aparecem no `<noscript>`).
- **Site "fora do ar" exige reconfirmação** em outra janela de tempo antes de virar
  argumento de proposta. Instabilidade intermitente não é site fora do ar.
- **Política de privacidade** é julgada pelos links que o site DECLARA, nunca por
  caminhos adivinhados.
- Site que bloqueia crawler por robots.txt **não** é tratado como problema. O robots.txt
  segue a RFC 9309: erro 4xx ao buscá-lo significa "sem restrição", não bloqueio.
- **Site montado por JavaScript** (HTML servido quase vazio): redes, formulário, política
  e banner de cookies não são verificáveis — a ausência deles não vira ponto nem frase.
  Continua valendo o que está no HTML servido (HTTPS, celular, sitemap, tag encontrada).
- **Site que não abriu** não gera "sem Instagram": o link poderia estar nele.

## Instagram e TikTok — seguidores

A varredura entrega o **@ e o link** dos perfis (achados no site e no cadastro). Seguidores
**não** entram na varredura: são consultados **sob demanda, um lead por clique**, na coluna
Instagram da tela de leads.

A fonte é o endpoint **business_discovery** da Graph API da Meta, que existe exatamente para
consultar perfis de terceiros. Exige um token de uma conta Comercial ou Criador de conteúdo
vinculada a uma Página do Facebook — o passo a passo está na tela **Configuração**. A Meta
libera cerca de **200 consultas por hora**; por isso a consulta é manual.

- Perfil **pessoal ou privado** não é devolvido pela API. Isso aparece como
  **"não disponível"** e nunca como "sem Instagram".
- Além dos seguidores vem a **data da última publicação** — perfil parado costuma valer mais
  como argumento de venda que número de seguidores.
- O TikTok segue sem contagem: não há API oficial equivalente.

## Arquivos

- `<FIND_DADOS>/saida/leads.db` (no servidor, `/data/saida/leads.db`) — banco com tudo que já foi coletado (deduplica entre rodadas
  e alimenta o "quem subiu e quem caiu")
- `saida/*.csv|xlsx|html` — exportações da linha de comando
- `nichos.json` — nichos prontos, edite à vontade

## Custos de referência (ago/2026)

Places API (New), Text Search Pro: ~US$32/1.000 requisições, com crédito mensal
gratuito. Cada página de 20 resultados = 1 requisição; busca de 120 = até 6 por termo.
BrasilAPI (CNPJ): gratuita. Nada mais é pago.
