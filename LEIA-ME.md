# SoulFork Radar

Prospecção de clientes por nicho e localização. O radar varre o Google Maps, encontra
as empresas da região, visita o site de cada uma, extrai **WhatsApp, e-mail, telefone,
Instagram, TikTok, Facebook e LinkedIn**, valida o **CNPJ** na base pública da Receita,
faz o **diagnóstico técnico** do site (HTTPS, celular, Pixel, GTM, LGPD, formulário) e
entrega um **score de oportunidade 0–100** com o motivo da primeira conversa já escrito.

## Instalador do Windows (jeito mais fácil)

Baixe o `SoulForkRadar-x.x.x-instalador.exe`, dê dois cliques e siga o assistente.
Na primeira vez o Windows pode mostrar **"O Windows protegeu o computador"** — isso é o
aviso padrão para programas novos, ainda sem reputação acumulada. Clique em
**Mais informações → Executar assim mesmo** e a instalação segue normal.

Depois de instalado, abra o Radar pelo atalho, vá em **Configuração** e cole sua chave da
Google Places API (o passo a passo de 5 minutos está na própria tela). Seus dados ficam em
`%APPDATA%\SoulForkRadar` — desinstalar o programa não apaga seus leads.

## Instalação a partir do código (alternativa)

Precisa de Python 3.10+ (python.org/downloads — no Windows, marque "Add to PATH").

```bash
cd soulfork-radar
pip install -r requirements.txt
```

### Chave do Google Places (obrigatória para buscar)

1. Acesse [console.cloud.google.com](https://console.cloud.google.com) e crie um projeto
2. Menu → **APIs e serviços** → **Biblioteca** → ative **Places API (New)**
3. Ative o faturamento (o Google dá crédito mensal gratuito; uma busca de 20 empresas
   custa centavos de dólar)
4. **Credenciais** → **Criar credenciais** → **Chave de API**
5. Em restrições da chave, restrinja à *Places API (New)*. **Não** use restrição por
   referer HTTP (a ferramenta chama do seu computador, não do navegador)
6. Copie `.env.example` para `.env` e cole a chave:

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
- Site que bloqueia crawler por robots.txt **não** é tratado como problema.

## Instagram e TikTok — seguidores

A ferramenta entrega o **@ e o link** dos perfis (achados no site e no cadastro).
Contagem de seguidores não é coletada automaticamente — as APIs oficiais não permitem
consultar perfil de terceiros. O fluxo da operação: os leads que forem para a fila são
enriquecidos no HypeAuditor (já conectado no Claude), só os que valem o crédito.

## Arquivos

- `saida/leads.db` — banco local com tudo que já foi coletado (deduplica entre rodadas
  e alimenta o "quem subiu e quem caiu")
- `saida/*.csv|xlsx|html` — exportações da linha de comando
- `nichos.json` — nichos prontos, edite à vontade

## Custos de referência (ago/2026)

Places API (New), Text Search Pro: ~US$32/1.000 requisições, com crédito mensal
gratuito. Cada página de 20 resultados = 1 requisição; busca de 120 = até 6 por termo.
BrasilAPI (CNPJ): gratuita. Nada mais é pago.
