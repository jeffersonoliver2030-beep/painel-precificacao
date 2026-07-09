import os
import json
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

# ==========================================
# CONFIGURAÇÕES INICIAIS E SEGURANÇA
# ==========================================
# Configuração do Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Configuração do Proxy Webshare (Seguras via Variáveis de Ambiente ou Padrão)
PROXY_USER = os.environ.get("PROXY_USER", "pcjoblvu-rotate")
PROXY_PASS = os.environ.get("PROXY_PASS", "leis7fqkehyb")
PROXY_HOST = os.environ.get("PROXY_HOST", "p.webshare.io")
PROXY_PORT = os.environ.get("PROXY_PORT", "80")

def obter_html_concorrente(url):
    """Faz a requisição usando o proxy rotativo do Webshare"""
    proxies = {
        "http": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}",
        "https": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"
    }
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resposta = requests.get(url, proxies=proxies, headers=headers, timeout=15)
        if resposta.status_code == 200:
            return resposta.text
        return None
    except Exception as e:
        print(f"Erro ao acessar o link via proxy: {str(e)}")
        return None

def limpar_html_para_ia(html_cru):
    """Passo 3: Extração Cirúrgica de Metadados (Open Graph e JSON-LD)"""
    if not html_cru:
        return ""
        
    soup = BeautifulSoup(html_cru, 'html.parser')
    info_extra = []

    # Busca nas Meta Tags (Ouro para e-commerce)
    meta_tags_alvo = [
        "og:title", "og:price:amount", "product:price:amount", 
        "twitter:title", "og:description", "og:site_name"
    ]
    
    for meta in soup.find_all("meta"):
        prop = meta.get("property") or meta.get("name")
        content = meta.get("content")
        if prop in meta_tags_alvo and content:
            info_extra.append(f"{prop}: {content.strip()}")

    # Captura os dados estruturados ocultos (JSON-LD)
    for script in soup.find_all("script", type="application/ld+json"):
        if script.string:
            info_extra.append(script.string.strip())
            
    if info_extra:
        print("-> [SUCESSO] Metadados/Meta tags encontrados!")
        return "\n".join(info_extra)[:15000]

    # Caso extremo: limpa o lixo e manda o esqueleto de texto
    for elemento in soup(["script", "style", "noscript", "iframe", "svg", "header", "footer", "nav"]):
        elemento.decompose()
        
    texto_limpo = soup.get_text(separator=' ')
    linhas = [linha.strip() for list_linha in texto_limpo.splitlines() for linha in [list_linha.strip()] if linha]
    
    return " ".join(linhas)[:20000]

def extrair_preco_com_gemini(texto_pagina, seu_preco="0.00"):
    """Passo 5: Análise Inteligente do Gemini 2.5 Flash"""
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = f"""
        Você é um robô analista de dados especialista em e-commerce.
        Sua missão é extrair o NOME do produto principal e o PREÇO atual de venda.
        
        Texto/Dados da página do concorrente:
        \"\"\"{texto_pagina}\"\"\"
        
        O preço do meu cliente para este mesmo produto é: R$ {seu_preco}

        REGRAS DE EXTRAÇÃO:
        1. Se houver chaves como "og:title" ou "name", extraia o título do produto dali.
        2. Se houver "og:price:amount", "price" ou valores numéricos perto do produto principal, capture o valor de venda.
        3. Ignore produtos recomendados, foque apenas no item principal da página.
        4. Retorne OBRIGATORIAMENTE apenas um objeto JSON válido (sem markdown, sem blocos de código) no seguinte formato:
        {{
            "produto_concorrente": "Nome do produto",
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
        print(f"Erro no Gemini: {str(e)}")
        return {
            "produto_concorrente": "Erro na análise de metadados",
            "preco_concorrente": 0.00,
            "meu_preco": seu_preco,
            "status_analise": "erro"
        }

# ==========================================
# ROTAS DO SERVIDOR (Ações do Botão)
# ==========================================
@app.route('/analisar-texto-extensao', methods=['POST'])
def analisar_texto_extensao():
    dados = request.get_json() or {}
    url_concorrente = dados.get('url_concorrente') or dados.get('conteudo_limpo') # Suporta os dois formatos de chamada
    seu_preco = dados.get('seu_preco', '0.00')

    if not url_concorrente:
        return jsonify({"erro": "A URL do concorrente é obrigatória."}), 400

    # Passo 2: Rastreamento com Proxy
    html_cru = obter_html_concorrente(url_concorrente) if url_concorrente.startswith("http") else url_concorrente
    
    if not html_cru:
        return jsonify({
            "title": "Não foi possível acessar o site concorrente",
            "price": 0.00,
            "produto_concorrente": "Não foi possível acessar o site",
            "preco_concorrente": 0.00,
            "meu_preco": seu_preco,
            "status_analise": "erro_conexao"
        })

    # Passo 3: Extração de Metadados
    conteudo_filtrado = limpar_html_para_ia(html_cru)

    # Passo 4: Trava de Segurança contra Erros / Bloqueios
    if not conteudo_filtrado or len(conteudo_filtrado.strip()) < 50:
        return jsonify({
            "title": "Erro: Link bloqueado ou inacessível",
            "price": 0.00,
            "produto_concorrente": "Não foi possível ler o site",
            "preco_concorrente": 0.00,
            "meu_preco": seu_preco,
            "status_analise": "erro"
        })

    # Passo 5: Executa a IA
    resultado_ia = extrair_preco_com_gemini(conteudo_filtrado, seu_preco)
    
    # Passo 6: Retorno perfeito formatado para o Lovable
    return jsonify({
        "title": resultado_ia.get("produto_concorrente", "Produto sem nome"),
        "price": resultado_ia.get("preco_concorrente", 0.00),
        "produto_concorrente": resultado_ia.get("produto_concorrente", "Produto sem nome"),
        "preco_concorrente": resultado_ia.get("preco_concorrente", 0.00),
        "meu_preco": resultado_ia.get("meu_preco", seu_preco),
        "status_analise": resultado_ia.get("status_analise", "sucesso")
    })

# ==========================================
# INICIALIZAÇÃO DO SERVIDOR (Ajustado Render)
# ==========================================
if __name__ == '__main__':
    porta = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=porta, debug=False)