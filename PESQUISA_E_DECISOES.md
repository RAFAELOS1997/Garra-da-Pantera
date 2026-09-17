# Pesquisa comparativa e decisões do programa

Esta versão não replica somente o Nativos3D. Ela combina ideias documentadas por ferramentas de edição e preparação para impressão:

- O Blender oferece seleção por laço, separação da seleção e separação por partes soltas. Isso orientou a revisão manual em várias vistas e a separação explícita das faces.
- O 3D Print Toolbox do Blender trata uma malha fechada (watertight) e sem arestas ou faces soltas como requisito de preparação. Isso orientou a trava de exportação.
- O PrusaSlicer diferencia objetos, partes, cortes planares e conectores; também permite escolher quais regiões manter unidas. Isso orientou a separação em dois objetos independentes e deixa conectores como uma etapa posterior à obtenção de uma interface confiável.
- A própria documentação da Prusa alerta que reparos automáticos nem sempre funcionam e que “Make solid” pode perder resolução. Por isso o programa não voxeliza nem remalha silenciosamente uma escultura detalhada.
- O OrcaSlicer oferece Split to Objects, Split to Parts, Mesh Boolean e ferramentas de montagem. Isso reforça a necessidade de preservar os dois objetos, validar cada um separadamente e preparar futuras opções de encaixe.

Fontes:

- https://docs.blender.org/manual/en/latest/modeling/meshes/tools/toolbar.html
- https://docs.blender.org/manual/en/5.0/modeling/meshes/editing/mesh/separate.html
- https://docs.blender.org/manual/en/3.0/addons/mesh/3d_print_toolbox.html
- https://help.prusa3d.com/article/cut-tool_1779
- https://help.prusa3d.com/article/corrupted-3d-models-for-printing_2205
- https://github.com/OrcaSlicer/OrcaSlicer/wiki/prepare_mesh_boolean
- https://github.com/OrcaSlicer/OrcaSlicer/wiki/prepare_assembly_tools

## Consequências práticas

1. O original nunca é sobrescrito.
2. A máscara do cabelo precisa ser revisada em várias vistas.
3. A seleção não é expandida automaticamente por uma regra semântica incerta.
4. O fechamento só é tentado quando a borda forma ciclos simples e pode ser projetada com segurança.
5. O programa produz um relatório mesmo quando recusa a exportação.
6. Reparos que sacrificam detalhes devem ser uma opção explícita em uma versão futura.
7. Pinos, cavilhas e encaixes só devem ser criados após a superfície de contato estar validada.

## Corte curvo inteligente — mecanismos estudados

- **CGAL Surface Mesh Segmentation** combina Shape Diameter Function, agrupamento suave e graph cut; o custo final também considera ângulo diedro e concavidade. A ideia aproveitada é separar “evidência por face” de “regularização da fronteira”. O SDF completo ainda não foi incorporado porque pressupõe uma malha fechada, orientada e sem interseções — condições que muitos STL de entrada não satisfazem.
- **libigl** oferece geodésicas exatas e pelo método do calor. Esses métodos sugerem a futura ferramenta de âncoras editáveis: o usuário posiciona pontos sobre a superfície e o contorno segue caminhos intrínsecos, em vez de linhas da tela.
- **MeshLib** descreve segmentação semiautomática guiada por curvatura, graph cut volumétrico, geodésicas sobre a superfície, reparo e booleans exatos/voxelizados. Isso confirma uma arquitetura híbrida: contorno superficial preciso primeiro e reconstrução voxel apenas como fallback.
- **MeshLab/VCGlib** fecha buracos com limite pelo número de arestas, prevenção heurística de auto-interseção, refinamento e suavização localizada das novas faces. O nosso fechamento conservador segue a mesma separação entre fechar, validar e só depois suavizar.
- **CGAL Polygon Mesh Processing** repara polygon soups, orienta faces, duplica elementos não-manifold quando necessário e costura bordas geometricamente idênticas. O programa atual faz uma versão menor dessa cascata e registra quando precisa recorrer à reconstrução.
- **PyMeshFix/MeshFix** busca um único sólido triangular fechado, removendo singularidades, auto-interseções e degenerações. Ele é adequado como backend opcional futuro, mas sua própria documentação alerta que assume um único sólido e pode produzir resultado grosseiro fora desse domínio.
- **SegFormer** usa um encoder hierárquico sem codificação posicional e um decoder leve para segmentação semântica. A máscara humana 2D é usada somente como evidência para a malha.
- **Self-Correction for Human Parsing** usa ciclos de pseudo-rótulos corrigidos. O paralelo adotado é permitir que correções manuais voltem ao classificador geométrico, em vez de aceitar a primeira máscara.

Implementação atual: probabilidades do classificador geométrico são custos unários; exemplos manuais são restrições fortes; adjacências recebem custo alto em áreas suaves e baixo em dobras com grande mudança de normal. Um corte mínimo produz a máscara contínua. O próximo avanço prioritário é acrescentar concavidade assinada, espessura local e âncoras geodésicas.

Fontes adicionais:

- https://doc.cgal.org/latest/Surface_mesh_segmentation/index.html
- https://doc.cgal.org/latest/Polygon_mesh_processing/index.html
- https://github.com/libigl/libigl
- https://github.com/MeshInspector/MeshLib
- https://github.com/pyvista/pymeshfix
- https://github.com/NVlabs/SegFormer
- https://github.com/PeikeLi/Self-Correction-Human-Parsing
