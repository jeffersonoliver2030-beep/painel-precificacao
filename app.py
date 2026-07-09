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
# Certifique-se de configurar a variável GEMINI_API_KEY no painel da Render!
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# ==========================================
# FUNÇÕES DE RASPAGEM E INTELIGÊNCIA ARTIFICIAL
# ==========================================

def obter_html_concorrente(url):
    """
    Acessa o site concorrente utilizando a rede de proxies residenciais
    rotativos do Webshare para burlar travas de segurança e capturar o HTML.
    """
    try:
        # Credenciais reais que o Webshare gerou para você
        PROXY_USER = "pcjoblvu-rotate"
        PROXY_PASS = "leis7fqkehyb"
        PROXY_HOST = "p.webshare.io"
        PROXY_PORT = "80"

        # Monta a URL de conexão do proxy estruturada de forma segura
        proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"
        
        config_proxies = {
            "http": proxy_url,
            "https": proxy_url
        }

        # Fingindo ser um navegador comum de computador
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"
        }

        # Faz a requisição de forma invisível passando pelo proxy residencial
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
    Versão Segura: Remove apenas códigos pesados e elementos que não contêm texto,
    preservando toda a estrutura de dados da página para que a IA não perca
    o nome e o preço real do produto por cortes agressivos.
    """
    if not html_cru:
        return ""
        
    soup = BeautifulSoup(html_cru, 'html.parser')
    
    # Remove apenas o que é código puramente computacional ou design fixo
    for elemento in soup(["script", "style", "noscript", "iframe", "svg", "header", "footer"]):
        elemento.decompose()
        
    # Extrai todo o texto restante da página de forma contínua
    texto_limpo = soup.get_text(separator=' ')
    
    # Limpa espaços em branco e linhas vazias
    linhas = [linha.strip() for list_linha in texto_limpo.splitlines() for linha in [list_linha.strip()] if linha]
    
    # Junta tudo e envia um bloco robusto de dados para a IA (até 20.000 caracteres)
    return " ".join(linhas)[:20000]


def extrair_preco_com_gemini(texto_pagina, seu_preco="0.00"):
    """
    Envia o texto limpo do e-commerce para o Gemini analisar de forma semântica
    e retornar o preço exato estruturado em JSON.
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = f"""
        Você é um robô especialista em inteligência de mercado e e-commerce.
        Analise o texto extraído de uma página de produto concorrente e encontre:
        1. O nome exato do produto principal em destaque na página.
        2. O preço real e atual de venda (Ignore parcelamentos de longo prazo e foque no valor à vista destacado ou no PIX se houver).
        
        Texto da página do concorrente:
        \"\"\"{texto_pagina}\"\"\"
        
        O preço do meu cliente para este mesmo produto é: R$ {seu_preco}

        Retorne OBRIGATORIAMENTE apenas um objeto JSON válido (sem markdown, sem blocos de código ```json, sem texto explicativo adicional) com o seguinte formato exato:
        {{
            "produto_concorrente": "Nome do produto encontrado aqui",
            "preco_concorrente": 0.00,
            "meu_preco": {seu_preco},
            "status_analise": "sucesso"
        }}
        Se você não conseguir identificar o produto ou o preço no texto fornecido, retorne o JSON com a estrutura idêntica, mas defina o "preco_concorrente" como 0.00 e o "status_analise" como "nao_encontrado".
        """
        
        resposta_ia = model.generate_content(prompt)
        texto_resposta = resposta_ia.text.strip()
        
        # Remove marcas de formatação de código de markdown que a IA às vezes adiciona
        if texto_resposta.startswith("```"):
            texto_resposta = texto_resposta.replace("```json", "").replace("```", "").strip()
            
        return json.loads(texto_resposta)
        
    except Exception as e:
        print(f"Erro ao processar dados no Gemini: {str(e)}")
        return {
            "produto_concorrente": "Erro na análise da IA",
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


@app.route('/analisar-produto', methods=['POST'])
def analisar_produto():
    """
    Rota principal acionada pelo painel do Lovable quando um usuário cola um link de monitoramento.
    """
    dados = request.get_json() or {}
    url_concorrente = dados.get('url_concorrente')
    seu_preco = dados.get('seu_preco', '0.00')

    if not url_concorrente:
        return jsonify({"erro": "A URL do concorrente é obrigatória."}), 400

    print(f"-> Nova requisição recebida para monitorar: {url_concorrente}")

    # 1. Faz o download usando o Proxy do Webshare
    html_cru = obter_html_concorrente(url_concorrente)
    
    if not html_cru:
        return jsonify({
            "produto_concorrente": "Não foi possível acessar o site concorrente",
            "preco_concorrente": 0.00,
            "meu_preco": seu_preco,
            "status_analise": "erro_conexao"
        }), 200

    # 2. Faz a limpeza pesada do HTML (Versão Otimizada)
    conteudo_filtrado = limpar_html_para_ia(html_cru)

    # 3. Passa o texto para o cérebro da Inteligência Artificial extrair o valor
    resultado_final = extrair_preco_com_gemini(conteudo_filtrado, seu_preco)
    
    return jsonify(resultado_final)


# Rota planejada para o plano Premium/Diamante via Extensão de Navegador
@app.route('/analisar-texto-extensao', methods=['POST'])
def analisar_texto_extensao():
    dados = request.get_json() or {}
    conteudo_limpo = dados.get('conteudo_limpo')
    seu_preco = dados.get('seu_preco', '0.00')

    if not conteudo_limpo:
        return jsonify({"erro": "Nenhum texto enviado pela extensão."}), 400

    resultado_final = extrair_preco_com_gemini(conteudo_limpo, seu_preco)
    return jsonify(resultado_final)


# ==========================================
# INICIALIZAÇÃO DO SERVIDOR
# ==========================================
if __name__ == '__main__':
    # Obtém a porta padrão do ambiente (necessário para rodar na Render)
    porta = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=porta, debug=True)