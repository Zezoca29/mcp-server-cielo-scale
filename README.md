# MCP Orchestrator - Multi-Language Code Analysis

Sistema MCP escalável para análise estática de código e geração de prompts para testes unitários. Suporta **Java**, **Python** e **TypeScript/JavaScript** através de runtimes especializados.

## 🏗️ Arquitetura

```
mcp-orchestrator/
├── server.py                      # Servidor MCP principal (FastMCP)
├── requirements.txt               # Dependências Python
├── package.json                   # Dependências Node.js
├── runtimes/
│   ├── python/
│   │   └── analyzer.py           # Analisador Python (AST)
│   └── ts/
│       └── analyzer.js           # Analisador TypeScript/JS (ts-morph)
├── java-analyzer/                 # Microserviço Spring Boot
│   ├── pom.xml
│   ├── src/main/java/com/mcporch/analyzer/
│   │   ├── JavaAnalyzerApplication.java
│   │   └── controller/CodeAnalyzerController.java
└── README.md
```

## 🚀 Instalação e Setup

### 1. Instalar Dependências Python
```bash
pip install -r requirements.txt
```

### 2. Instalar Dependências Node.js
```bash
npm install
```

### 3. Configurar e Rodar Spring Boot (Java)
```bash
cd java-analyzer
mvn spring-boot:run
```
O serviço Java ficará disponível em `http://localhost:8080`

### 4. Iniciar o MCP Orchestrator
```bash
python server.py
```

## 🛠️ Tools Disponíveis

### 1. `analyze_function(language: str, code: str)`
Análise estática de funções em Java/Python/TypeScript.

**Input:**
```json
{
  "language": "python",
  "code": "def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)"
}
```

**Output:**
```json
{
  "language": "python",
  "functions": [{"name": "fibonacci", "inputs": [...], "outputs": [...]}],
  "complexity": 3,
  "branches": 1,
  "side_effects": []
}
```

### 2. `summarize_flow(summary: dict)`
Resume fluxo de execução e identifica caminhos críticos.

**Output:**
```json
{
  "overview": "Functions: ['fibonacci']. Inputs: ['n: int']. Outputs: ['int']...",
  "key_paths": ["main_path_1"],
  "edge_cases": ["null/None inputs", "boundary numbers", ...],
  "io_matrix": [{"inputs": ["n: int"], "expected": ["int"]}],
  "risks": ["high complexity paths"]
}
```

### 3. `build_prompt(flow: dict)`
Gera prompt otimizado para LLM criar testes unitários.

**Output:**
```json
{
  "prompt": "Você é um agente especializado em geração de testes...",
  "tokens_est": 245,
  "guardrails": ["Não invente dependências", "Cubra todos os branches", ...]
}
```

### 4. `run_full_pipeline(language: str, code: str)` ⭐
**Super-tool** que executa todo o pipeline em sequência.

**Output:**
```json
{
  "analysis": {...},
  "flow": {...}, 
  "prompt": {...},
  "meta": {
    "started_at": 1703123456.789,
    "finished_at": 1703123456.892,
    "duration_ms": 103,
    "errors": [],
    "language": "python",
    "steps_completed": 3
  }
}
```

## 📋 Exemplos de Uso

### Python
```python
# Código de exemplo
code = """
def calculate_discount(price, discount_percent, customer_type='regular'):
    if price <= 0:
        raise ValueError("Price must be positive")
    
    if customer_type == 'premium':
        discount_percent += 5
    
    final_price = price * (1 - discount_percent / 100)
    return max(0, final_price)
"""

# Chamar MCP tool
result = run_full_pipeline("python", code)
prompt = result["prompt"]["prompt"]
# Usar prompt no seu LLM favorito para gerar testes
```

### Java
```java
// Código de exemplo
String code = """
public class Calculator {
    public static int divide(int a, int b) {
        if (b == 0) {
            throw new ArithmeticException("Division by zero");
        }
        return a / b;
    }
}
""";

// Chamar MCP tool
Map<String, Object> result = run_full_pipeline("java", code);
```

### TypeScript
```typescript
// Código de exemplo
const code = `
async function fetchUserData(userId: number): Promise<User | null> {
    try {
        const response = await fetch(\`/api/users/\${userId}\`);
        if (!response.ok) {
            return null;
        }
        return await response.json();
    } catch (error) {
        console.error('Failed to fetch user:', error);
        return null;
    }
}
`;

// Chamar MCP tool
const result = run_full_pipeline("typescript", code);
```

## 🔍 Recursos MCP

### Cache de Análises
```
mcp://last-analyses
```
Retorna as últimas 10 análises executadas com timestamp.

### Cache de Prompts
```
mcp://last-prompts  
```
Retorna os últimos 10 prompts gerados com preview e estimativa de tokens.

## ⚙️ Configuração Avançada

### Timeouts
- Análises Python/TS: 10 segundos
- Requisições HTTP Java: 10 segundos

### Tratamento de Erros
- Todos os erros são capturados e retornados em `meta.errors[]`
- Falhas em uma etapa não interrompem o pipeline completo
- Logs detalhados em stderr

### Normalização de Saída
Todas as linguagens retornam o mesmo contrato JSON:
```json
{
  "functions": [...],
  "inputs": [...],
  "outputs": [...], 
  "complexity": int,
  "branches": int,
  "side_effects": [...]
}
```

## 🧪 Teste Rápido

### 1. Testar Python
```bash
echo 'def hello(name): return f"Hello {name}"' | python runtimes/python/analyzer.py
```

### 2. Testar TypeScript
```bash
echo 'function add(a: number, b: number): number { return a + b; }' | node runtimes/ts/analyzer.js
```

### 3. Testar Java
```bash
curl -X POST http://localhost:8080/analyze \
  -H "Content-Type: application/json" \
  -d '{"code": "public int add(int a, int b) { return a + b; }"}'
```

### 4. Testar Pipeline Completo
```python
from server import run_full_pipeline

result = run_full_pipeline("python", "def square(x): return x * x")
print(result["prompt"]["prompt"])
```

## 📊 Métricas Coletadas

- **Functions**: Lista de funções encontradas
- **Inputs**: Parâmetros com tipos (quando disponível)  
- **Outputs**: Tipos de retorno inferidos/declarados
- **Complexity**: Complexidade ciclomática aproximada
- **Branches**: Número de caminhos condicionais
- **Side Effects**: IO, rede, modificação de estado, etc.

## 🔧 Resolução de Problemas

### Java Analyzer não responde
```bash
# Verificar se está rodando
curl http://localhost:8080/health

# Reiniciar se necessário
cd java-analyzer && mvn spring-boot:run
```

### Erro de dependência Python/Node
```bash
# Reinstalar dependências
pip install -r requirements.txt
npm install
```

### Timeout nos analyzers
- Verificar se os scripts têm permissão de execução
- Testar os analyzers individualmente
- Aumentar timeout em `server.py` se necessário

## 📝 Licença

MIT License - Use livremente em seus projetos!

---

**Próximos passos**: Integre este MCP ao seu workflow de desenvolvimento para gerar testes automaticamente a partir do código analisado! 🚀