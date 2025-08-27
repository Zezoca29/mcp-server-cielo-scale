#!/usr/bin/env node
/**
 * TypeScript/JavaScript AST Analyzer for MCP Orchestrator
 * Analyzes TypeScript/JavaScript code and extracts functions, inputs, outputs, complexity, branches
 */

const { Project, SyntaxKind } = require('ts-morph');

class TypeScriptAnalyzer {
    constructor() {
        this.functions = [];
        this.totalBranches = 0;
        this.complexity = 0;
        this.sideEffects = new Set();
    }

    analyze(code) {
        try {
            const project = new Project({ useInMemoryFileSystem: true });
            const sourceFile = project.createSourceFile('temp.ts', code);
            
            this.visitNode(sourceFile);
            
            return {
                functions: this.functions,
                inputs: this.collectAllInputs(),
                outputs: this.collectAllOutputs(),
                complexity: this.complexity,
                branches: this.totalBranches,
                side_effects: Array.from(this.sideEffects)
            };
        } catch (error) {
            return { error: `Analysis error: ${error.message}` };
        }
    }

    visitNode(node) {
        if (node.getKind() === SyntaxKind.FunctionDeclaration ||
            node.getKind() === SyntaxKind.ArrowFunction ||
            node.getKind() === SyntaxKind.FunctionExpression ||
            node.getKind() === SyntaxKind.MethodDeclaration) {
            
            this.analyzeFunctionNode(node);
        }

        // Visit conditional statements
        if (node.getKind() === SyntaxKind.IfStatement) {
            this.totalBranches++;
            this.complexity++;
        }

        // Visit loops
        if (node.getKind() === SyntaxKind.ForStatement ||
            node.getKind() === SyntaxKind.WhileStatement ||
            node.getKind() === SyntaxKind.DoStatement ||
            node.getKind() === SyntaxKind.ForInStatement ||
            node.getKind() === SyntaxKind.ForOfStatement) {
            this.totalBranches++;
            this.complexity++;
        }

        // Visit try-catch
        if (node.getKind() === SyntaxKind.TryStatement) {
            this.totalBranches += 2; // try + catch
            this.complexity += 2;
        }

        // Visit switch statements
        if (node.getKind() === SyntaxKind.SwitchStatement) {
            const caseCount = node.getCaseBlock().getClauses().length;
            this.totalBranches += Math.max(1, caseCount);
            this.complexity += Math.max(1, caseCount);
        }

        // Detect side effects
        if (node.getKind() === SyntaxKind.CallExpression) {
            this.detectSideEffects(node);
        }

        // Continue visiting children
        node.forEachChild(child => this.visitNode(child));
    }

    analyzeFunctionNode(node) {
        const funcInfo = {
            name: this.getFunctionName(node),
            inputs: this.extractInputs(node),
            outputs: this.extractOutputs(node),
            line_start: node.getStartLineNumber(),
            line_end: node.getEndLineNumber(),
            branches: 0,
            local_complexity: 1
        };

        // Count branches within this function
        const currentBranches = this.totalBranches;
        const currentComplexity = this.complexity;
        
        node.forEachChild(child => this.visitNode(child));
        
        funcInfo.branches = this.totalBranches - currentBranches;
        funcInfo.local_complexity = this.complexity - currentComplexity + 1;

        this.functions.push(funcInfo);
    }

    getFunctionName(node) {
        if (node.getKind() === SyntaxKind.FunctionDeclaration) {
            return node.getName() || '<anonymous>';
        }
        if (node.getKind() === SyntaxKind.MethodDeclaration) {
            return node.getName();
        }
        if (node.getKind() === SyntaxKind.ArrowFunction || 
            node.getKind() === SyntaxKind.FunctionExpression) {
            // Try to get name from variable assignment
            const parent = node.getParent();
            if (parent && parent.getKind() === SyntaxKind.VariableDeclaration) {
                return parent.getName();
            }
            return '<anonymous>';
        }
        return '<unknown>';
    }

    extractInputs(node) {
        const inputs = [];
        
        if (node.getParameters) {
            const parameters = node.getParameters();
            for (const param of parameters) {
                inputs.push({
                    name: param.getName(),
                    type: param.getTypeNode() ? param.getTypeNode().getText() : 'any',
                    kind: 'parameter',
                    optional: param.hasQuestionToken()
                });
            }
        }
        
        return inputs;
    }

    extractOutputs(node) {
        const outputs = [];
        
        if (node.getReturnTypeNode) {
            const returnType = node.getReturnTypeNode();
            if (returnType) {
                outputs.push(returnType.getText());
            }
        }
        
        if (outputs.length === 0) {
            // Try to infer from return statements
            const returnStatements = node.getDescendantsOfKind(SyntaxKind.ReturnStatement);
            if (returnStatements.length > 0) {
                outputs.push('inferred');
            } else {
                outputs.push('void');
            }
        }
        
        return outputs;
    }

    detectSideEffects(callNode) {
        const expression = callNode.getExpression();
        
        if (expression.getKind() === SyntaxKind.Identifier) {
            const funcName = expression.getText();
            if (['console.log', 'alert', 'confirm', 'prompt'].includes(funcName)) {
                this.sideEffects.add('io_operations');
            }
        }
        
        if (expression.getKind() === SyntaxKind.PropertyAccessExpression) {
            const propAccess = expression;
            const propertyName = propAccess.getName();
            
            if (['fetch', 'XMLHttpRequest', 'axios'].includes(propertyName) ||
                propAccess.getText().includes('.fetch(') ||
                propAccess.getText().includes('.post(') ||
                propAccess.getText().includes('.get(')) {
                this.sideEffects.add('network_operations');
            }
            
            if (['localStorage', 'sessionStorage', 'indexedDB'].includes(propertyName)) {
                this.sideEffects.add('storage_operations');
            }
            
            if (propertyName === 'log' && propAccess.getExpression().getText() === 'console') {
                this.sideEffects.add('io_operations');
            }
        }
        
        // Detect async operations
        if (callNode.getParent() && callNode.getParent().getKind() === SyntaxKind.AwaitExpression) {
            this.sideEffects.add('async_operations');
        }
    }

    collectAllInputs() {
        const allInputs = [];
        for (const func of this.functions) {
            allInputs.push(...func.inputs.map(input => `${input.name}: ${input.type}`));
        }
        return allInputs;
    }

    collectAllOutputs() {
        const allOutputs = [];
        for (const func of this.functions) {
            allOutputs.push(...func.outputs);
        }
        return allOutputs;
    }
}

// Main execution
if (require.main === module) {
    let input = '';
    
    process.stdin.setEncoding('utf8');
    process.stdin.on('readable', () => {
        const chunk = process.stdin.read();
        if (chunk !== null) {
            input += chunk;
        }
    });
    
    process.stdin.on('end', () => {
        const analyzer = new TypeScriptAnalyzer();
        const result = analyzer.analyze(input);
        console.log(JSON.stringify(result, null, 2));
    });
}

module.exports = TypeScriptAnalyzer;