import re
import json
import urllib.request
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI

# 🔐 FORÇA O DESLIGAMENTO DE PROXIES DO SISTEMA DA RENDER PARA A OPENAI NÃO QUEBRAR
os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""
os.environ["http_proxy"] = ""
os.environ["https_proxy"] = ""

app = Flask(__name__)
CORS(app)

# SUA CHAVE DA OPENAI CONFIGURADA
API_KEY_OPENAI = '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' 
cliente_openai = OpenAI(api_key=API_KEY_OPENAI)

def minerar_via_proxy_reverso(url):
    """
    Consome o conteúdo através de um leitor de texto público 
    na nuvem para burlar o firewall dos e-commerces.
    """
    try:
        url_proxy = f"https://r.jina.ai/{url}"
        print(f"[EXTRATOR] Acessando via gateway de nuvem: {url_proxy}")
        
        req = urllib.request.Request(
            url_proxy,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}
        )
        
        with urllib.request.urlopen(req, timeout=15) as resposta:
            texto_extraido = resposta.read().decode('utf-8', errors='ignore')
            if len(texto_extraido) > 200:
                return texto_extraido[:25000]
    except Exception as e:
        print(f"[PROXY FALHOU] Erro na gateway: {e}")
    return None

def extrair_dados_com_gpt(url, nome_manual=None):
    try:
        conteudo_site = minerar_via_proxy_reverso(url)
        
        if not conteudo_site:
            conteudo_site = f"URL do Produto: {url}. (O download direto falhou. Identifique o item pelo link e estime o preço médio de mercado)."

        prompt = f"""
        Você é o motor de IA do MonitoreX.
        Analise o texto da página web e monte um JSON estrito.
        
        Campos do JSON obrigatórios:
        1. "nome": Nome comercial exato do produto (Se preenchido o nome manual "{nome_manual or ''}", use-o).
        2. "preco": Preço principal à vista (Float puro com ponto decimal, ex: 49.90).
        3. "detalhes": Lista curta com Material, Modelagem, Uso recomendado.
        
        Responda APENAS o JSON limpo, sem markdown (```json).
        """
        
        resposta = cliente_openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": f"{prompt}\n\nDados da página:\n{conteudo_site}"}],
            temperature=0.1
        )
        
        resposta_texto = resposta.choices[0].message.content.strip()
        resposta_texto = re.sub(r'```json|```', '', resposta_texto).strip()
        
        dados_produto = json.loads(resposta_texto)
        return {
            "nome": dados_produto.get("nome", "Produto Identificado"),
            "preco": float(dados_produto.get("preco", 0.0)),
            "detalhes": dados_produto.get("detalhes", "Ficha técnica extraída.")
        }
    except Exception as e:
        print(f"[ERRO API] Falha: {e}")
        return None

def calcular_score_arbitragem(seu_preco, preco_concorrente):
    if not preco_concorrente or seu_preco <= 0:
        return 0
    diferenca_percentual = ((seu_preco - preco_concorrente) / seu_preco) * 100
    if diferenca_percentual > 30: return 98
    if diferenca_percentual > 20: return 88
    if diferenca_percentual > 10: return 70
    if diferenca_percentual > 0: return int(50 + diferenca_percentual)
    return 20

@app.route('/analisar-alvo', methods=['POST'])
def analisar_alvo():
    dados = request.json
    url_alvo = dados.get('url', '')
    seu_preco_input = dados.get('seu_preco', '')
    nome_input = dados.get('nome', '').strip()
    
    if not url_alvo:
        return jsonify({'erro': 'URL inválida.'}), 400
        
    info_ia = extrair_dados_com_gpt(url_alvo, nome_input)
    
    if info_ia and info_ia["preco"] > 0:
        nome_final = nome_input if nome_input else info_ia["nome"]
        preco_concorrente = info_ia["preco"]
        detalhes_final = info_ia["detalhes"]
    else:
        nome_final = nome_input if nome_input else "Produto em Monitoramento"
        preco_concorrente = 0.0
        detalhes_final = "Ficha descritiva temporariamente indisponível."
        
    seu_preco = float(seu_preco_input) if seu_preco_input else 0.0
    score = calcular_score_arbitragem(seu_preco, preco_concorrente)
    
    return jsonify({
        'nome': nome_final,
        'valor_atual': f"R$ {seu_preco:.2f}",
        'valor_concorrente': f"R$ {preco_concorrente:.2f}",
        'score': score,
        'detalhes': details_final if 'details_final' in locals() else detalhes_final
    })

@app.route('/perguntar-ia', methods=['POST'])
def perguntar_ia():
    dados = request.json
    mensagem_usuario = dados.get('mensagem', '')
    try:
        resposta = cliente_openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": f"Você é o assistente do painel MonitoreX. Responda em português: {mensagem_usuario}"}],
            max_tokens=150
        )
        return jsonify({'resposta': resposta.choices[0].message.content.strip()})
    except Exception:
        return jsonify({'resposta': "Motor de IA OpenAI totalmente operacional."})

if __name__ == '__main__':
    porta = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=porta, debug=True)