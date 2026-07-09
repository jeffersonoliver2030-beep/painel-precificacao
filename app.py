import os
import re
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai  # Biblioteca oficial do Gemini

app = Flask(__name__)
CORS(app)

# Configura a chave do Gemini buscando de forma segura do ambiente
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Inicializa o modelo usando a nomenclatura estável atual
model = genai.GenerativeModel('gemini-2.5-flash')

def limpar_html_para_ia(html_puro):
    """Remove o excesso de código do site para economizar seus tokens no Gemini"""
    soup = BeautifulSoup(html_puro, 'html.parser')
    for elemento in soup(["script", "style", "nav", "footer", "iframe", "header"]):
        elemento.decompose()
    return re.sub(r'\s+', ' ', soup.get_text())[:8000]

@app.route('/analisar-alvo', methods=['POST'])
def analisar_alvo():
    dados = request.get_json()
    url = dados.get('url')
    seu_preco = dados.get('seu_preco', '0.00')
    nome_opcional = dados.get('nome', '')

    if not url:
        return jsonify({"erro": True, "mensagem": "URL não fornecida"}), 400

    try:
        # 1. Simula um navegador para o e-commerce não bloquear o acesso
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"
        }
        
        resposta_site = requests.get(url, headers=headers, timeout=15)
        
        if resposta_site.status_code != 200:
            return jsonify({
                "erro": False,
                "score": 0,
                "nome": nome_opcional or "Erro de Acesso",
                "detalhes": f"O site bloqueou o acesso direto do robô (Código: {resposta_site.status_code}).",
                "valor_atual": seu_preco,
                "valor_concorrente": "Não localizado"
            })

        # 2. Limpa o conteúdo da página
        conteudo_limpo = limpar_html_para_ia(resposta_site.text)

        # 3. Prompt estruturado para o Gemini extrair os dados em JSON puro
        prompt = f"""
        Você é um extrator de dados preciso que responde apenas em JSON puro.
        Analise o texto estruturado de uma página de produto e capture o preço real de venda atual.
        Ignore valores antigos riscados ou preços de parcelamento longo se houver valor à vista.
        Se encontrar o nome do produto no texto, capture também.

        Texto da página:
        {conteudo_limpo}

        Responda rigorosamente no formato JSON abaixo, sem marcações markdown como ```json ou textos adicionais:
        {{
            "nome": "Nome do produto",
            "preco_alvo": 159.90,
            "detalhes": "Condição ou observação sobre o preço"
        }}
        Se não encontrar nenhum preço viável, retorne 0 em preco_alvo.
        """

        # 4. Chama a API do Gemini
        resposta_ia = model.generate_content(prompt)
        texto_json = resposta_ia.text.strip()
        
        # Garante a remoção de possíveis marcações markdown que a IA possa colocar
        texto_json = re.sub(r'```json\s*|```', '', texto_json)
        dados_ia = json.loads(texto_json)

        preco_concorrente = dados_ia.get("preco_alvo", 0)
        nome_produto = nome_opcional or dados_ia.get("nome", "Produto em Monitoramento")
        detalhes = dados_ia.get("detalhes", "Extraído via Inteligência Semântica Google Gemini.")

        # 5. Cálculo de arbitragem para gerar o Score de oportunidade
        try:
            v_seu = float(seu_preco)
            v_conc = float(preco_concorrente)
            score = int(((v_conc - v_seu) / v_conc) * 100) if v_conc > 0 else 0
            score = max(0, min(100, score))
        except:
            score = 0

        return jsonify({
            "erro": False,
            "score": score,
            "nome": nome_produto,
            "detalhes": detalhes,
            "valor_atual": v_seu,
            "valor_concorrente": v_conc
        })

    except Exception as e:
        print(f"Erro interno: {str(e)}")
        return jsonify({"erro": True, "mensagem": f"Erro interno: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
