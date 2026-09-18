# Garra da Pantera

Aplicativo desktop local para separar **qualquer elemento visível** de uma malha 3D e gerar duas peças imprimíveis. O usuário descreve o alvo — cabelo, espada, capa, braço, base, acessório ou outro objeto —, confirma a máscara e o programa aprende a fronteira sobre a geometria.

## O que ele faz

- Abre STL, OBJ e PLY; cria uma cópia de trabalho para malhas acima de um milhão de faces.
- Segmenta classes humanas com SegFormer e alvos arbitrários por texto com CLIPSeg.
- Projeta a máscara 2D na vista ortográfica atual como exemplos, sem enviar a imagem ou a malha à internet.
- Aprende com marcações positivas e áreas protegidas em várias vistas.
- Calcula corte curvo por graph cut usando confiança, dobra, concavidade, comprimento de aresta e sensibilidade angular.
- Permite corrigir por laço, expandir, retrair, remover fragmentos e desfazer.
- Repara cada lado do corte (reparo conservador, PyMeshFix e, em último caso, reconstrução volumétrica) e bloqueia o STL se a validação topológica falhar.
- Gera conectores de pino/furo ao longo da linha de corte, para que as duas peças se encaixem na montagem física.
- Revalida os arquivos depois da gravação.

## Instalação no Windows

```powershell
.\setup.ps1
```

Depois, abra `abrir_programa.bat`. Os pesos são baixados na primeira utilização: `mattmdjaga/segformer_b2_clothes` para anatomia/roupa e `CIDAS/clipseg-rd64-refined` para texto aberto.

## Fluxo recomendado

1. Abra a malha e execute **Diagnóstico inicial**.
2. Escreva o alvo no campo **ALVO**.
3. Escolha uma vista compatível e clique **Analisar imagem**.
4. Confira a prévia: verde é alvo e rosa é proteção.
5. Ensine exceções em pelo menos duas vistas com **É o alvo** e **Proteger**.
6. Clique **Reconhecer no 3D**, ajuste confiança e ângulo e refine a seleção laranja.
7. Salve o projeto e clique **Cortar, autocorrigir e validar**.

A exportação cria `alvo_<nome>.stl`, `restante.stl` e `validacao_separacao.json` em uma pasta nova. Reconstruções volumétricas registram resolução e deslocamento estimado. Por padrão, pinos e furos de encaixe são adicionados ao longo do corte (espaçamento e folga configuráveis na barra lateral); se a operação booleana não deixar a malha válida, o programa exporta sem conectores e registra o motivo no relatório.

## Limitações atuais

- A projeção 2D–3D usa alinhamento ortográfico normalizado; diferenças fortes de perspectiva e pose pedem correção manual.
- Segmentação por texto é uma hipótese visual. Marcações manuais têm prioridade absoluta.
- Reconstrução voxel pode suavizar detalhes menores que cerca de dois voxels.
- Validade topológica não garante espessura, suporte ou encaixe físico adequados.

## Desenvolvimento

Agentes e colaboradores devem ler [AGENTS.md](AGENTS.md), [ARCHITECTURE.md](ARCHITECTURE.md), [UPDATE_POLICY.md](UPDATE_POLICY.md) e [PESQUISA_E_DECISOES.md](PESQUISA_E_DECISOES.md).

```powershell
.\.venv\Scripts\python.exe -m py_compile garra_da_pantera.py hair_separator.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Malhas, imagens, pesos, projetos e relatórios do usuário são excluídos pelo `.gitignore`.
