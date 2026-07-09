import os
import json
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

# ==========================================
# CONFIGURAÇÕES INICIAIS
# ==========================================
app = Flask(__name__)
CORS(app)  # Permite que o Lovable se conecte com este backend

# Configuração da API Key do Google Gemini
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Credenciais do proxy Webshare (Mantidas com fallback seguro para rodar direto)
PROXY_USER = os.environ.get("PROXY_USER", "pcjoblvu-rotate")
PROXY_PASS = os.environ.get("PROXY_PASS", "leis7fqkehyb")
PROXY_HOST = os.environ.get("PROXY_HOST", "p.webshare.io")
PROXY_PORT = os.environ.get("PROXY_PORT", "80")

# ==========================================
# FUNÇÕES DE RASPAGEM E INTELIGÊNCIA ARTIFICIAL
# ==========================================

def obter_html_concorrente(url):
    """
    Acessa o site concorrente utilizando a rede de proxies residenciais
    rotativos do Webshare para reduzir bloqueios e capturar o HTML.
    """
    try:
        if not PROXY_USER or not PROXY_PASS:
            print("Erro: variáveis PROXY_USER / PROXY_PASS não configuradas no ambiente.")
            return None

        proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"

        config_proxies = {
            "http": proxy_url,
            "https": proxy_url
        }

        # Fingindo ser un navegador comum de computador
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"
        }

        resposta_site = requests.get(url, proxies=config_proxies, headers=headers, timeout=20)

        # LOGS DE MONITORAMENTO (Para você ver tudo no terminal da Render)
        print("--- DEBUG PROXY WEBSHARE ---")
        print(f"URL Buscada: {url}")
        print(f"Status Code do Site Concorrente: {resposta_site.status_code}")
        print(f"Tamanho do HTML recuperado: {len(resposta_site.text)} caracteres")
        print("----------------------------")

        if resposta_site.status_code == 200:
            return resposta_site.text
        else:
            print(f"Erro ao acessar o site. Status recebido: {resposta_site.status_code}")
            return None

    except Exception as e:
        print(f"Erro crítico na conexão com o proxy: {str(e)}")
        return None


def limpar_html_para_ia(html_cru):
    """
    Estratégia: procura primeiro pelas Meta Tags (Open Graph), que ficam no
    cabeçalho da página e são estáticas, e pelos dados estruturados JSON-LD.
    Se não encontrar nada, cai para o texto visível da página como reserva.
    """
    if not html_cru:
        return ""

    soup = BeautifulSoup(html_cru, 'html.parser')
    info_extra = []

    # 1. Busca nas Meta Tags (Ouro para e-commerce)
    meta_tags_alvo = [
        "og:title", "og:price:amount", "product:price:amount",
        "twitter:title", "og:description", "og:site_name"
    ]

    for meta in soup.find_all("meta"):
        prop = meta.get("property") or meta.get("name")
        content = meta.get("content")
        if prop in meta_tags_alvo and content:
            info_extra.append(f"{prop}: {content.strip()}")

    # 2. Tenta capturar também os metadados ocultos do produto (JSON-LD)
    for script in soup.find_all("script", type="application/ld+json"):
        if script.string:
            info_extra.append(script.string.strip())

    # 3. Se achou meta tags ou JSON-LD, prioriza totalmente esses dados puros
    if info_extra:
        print("-> [SUCESSO] Metadados/Meta tags encontrados na página!")
        return "\n".join(info_extra)[:15000]

    # 4. Se não achar nada, limpa o lixo computacional e manda o esqueleto completo
    for elemento in soup(["script", "style", "noscript", "iframe", "svg", "header", "footer", "nav"]):
        elemento.decompose()

    texto_limpo = soup.get_text(separator=' ')
    linhas = [linha.strip() for list_linha in texto_limpo.splitlines() for linha in [list_linha.strip()] if linha]

    return " ".join(linhas)[:20000]


def extrair_preco_com_gemini(texto_pagina, seu_preco="0.00"):
    """
    Instrui o Gemini a analisar semanticamente os dados crus ou estruturados,
    garantindo a captura mesmo que os dados estejam em formato JSON nativo do site.
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')

        prompt = f"""
        Você é um robô analista de dados especialista em e-commerce.
        Sua missão é extrair o NOME do produto principal e o PREÇO atual de venda.
        O texto fornecido pode ser um emaranhado de texto comum, metadados open graph ou um objeto JSON (JSON-LD).

        Texto/Dados da página do concorrente:
        \"\"\"{texto_pagina}\"\"\"

        O preço do meu cliente para este mesmo produto é: R$ {seu_preco}

        REGRAS DE EXTRAÇÃO:
        1. Se houver chaves como "og:title" ou "name", extraia o título do produto dali.
        2. Se houver "og:price:amount", "price" ou valores numéricos explícitos perto do produto principal, capture o valor de venda corrente.
        3. Ignore produtos recomendados, foque apenas no item principal da página.
        4. Retorne OBRIGATORIAMENTE apenas um objeto JSON válido (sem markdown, sem blocos de código ```json, sem texto explicativo adicional) com o seguinte formato exato:
        {{
            "produto_concorrente": "Nome do produto encontrado aqui",
            "preco_concorrente": 0.00,
            "meu_preco": {seu_preco},
            "status_analise": "sucesso"
        }}
        """

        resposta_ia = model.generate_content(prompt)
        texto_resposta = resposta_ia.text.strip()

        if texto_resposta.startswith("```"):
            texto_resposta = texto_resposta.replace("```json", "").replace("```", "").strip()

        return json.loads(texto_resposta)

    except Exception as e:
        print(f"Erro ao processar dados no Gemini: {str(e)}")
        return {
            "produto_concorrente": "Erro na análise de metadados",
            "preco_concorrente": 0.00,
            "meu_preco": seu_preco,
            "status_analise": "erro"
        }


# ==========================================
# ROTAS DA API (CONEXÃO COM O LOVABLE)
# ==========================================

@app.route('/', methods=['GET'])
def pagina_inicial():
    return jsonify({"status": "online", "mensagem": "Servidor do Monitor de Concorrentes ativo!"})


@app.route('/analisar-texto-extensao', methods=['POST'])
def analisar_texto_extensao():
    """
    Rota principal acionada pelo painel do Lovable. Segue o fluxo:
      1. valida a URL recebida
      2. baixa o HTML via proxy Webshare
      3. extrai metadados (Open Graph / JSON-LD)
      4. trava de segurança: bloqueia se o conteúdo vir vazio/curto demais
      5. manda para o Gemini analisar e formatar
      6. devolve sempre as chaves "title" e "price" (padrão exigido pelo Lovable)
    """
    dados = request.get_json() or {}
    url_concorrente = dados.get('url_concorrente') or dados.get('conteudo_limpo') # Mantém compatibilidade com chamadas antigas
    seu_preco = dados.get('seu_preco', '0.00')

    if not url_concorrente:
        return jsonify({"erro": "A URL do concorrente é obrigatória."}), 400

    print(f"-> Nova requisição recebida para monitorar: {url_concorrente}")

    # 1. Faz o download usando o Proxy do Webshare
    html_cru = obter_html_concorrente(url_concorrente) if url_concorrente.startswith("http") else url_concorrente

    if not html_cru:
        return jsonify({
            "title": "Não foi possível acessar o site concorrente",
            "price": 0.00,
            "produto_concorrente": "Não foi possível acessar o site concorrente",
            "preco_concorrente": 0.00,
            "meu_preco": seu_preco,
            "status_analise": "erro_conexao"
        }), 200

    # 2. Faz a limpeza pesada do HTML (meta tags / JSON-LD / texto)
    conteudo_filtrado = limpar_html_para_ia(html_cru)

    # 3. TRAVA DE SEGURANÇA: se veio pouco ou nenhum conteúdo útil, interrompe aqui
    if not conteudo_filtrado or len(conteudo_filtrado.strip()) < 50:
        return jsonify({
            "title": "Erro: Link bloqueado ou inacessível",
            "price": 0.00,
            "produto_concorrente": "Não foi possível ler o site",
            "preco_concorrente": 0.00,
            "meu_preco": seu_preco,
            "status_analise": "erro"
        }), 200

    # 4. Passa o texto limpo para o Gemini extrair nome e preço
    resultado_ia = extrair_preco_com_gemini(conteudo_filtrado, seu_preco)

    # 5. Formata a resposta final garantindo as chaves "title" e "price" exigidas pelo Lovable
    resultado_formatado = {
        "title": resultado_ia.get("produto_concorrente", "Produto sem nome"),
        "price": resultado_ia.get("preco_concorrente", 0.00),
        "produto_concorrente": resultado_ia.get("produto_concorrente", "Produto sem nome"),
        "preco_concorrente": resultado_ia.get("preco_concorrente", 0.00),
        "meu_preco": resultado_ia.get("meu_preco", seu_preco),
        "status_analise": resultado_ia.get("status_analise", "sucesso")
    }

    return jsonify(resultado_formatado)


# ==========================================
# INICIALIZAÇÃO DO SERVIDOR
# ==========================================
if __name__ == '__main__':
    # Obtém a porta padrão do ambiente (necessário para rodar na Render)
    porta = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=porta, debug=False)