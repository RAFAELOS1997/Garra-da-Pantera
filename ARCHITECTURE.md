# Arquitetura da Garra da Pantera

1. **Entrada e diagnóstico** — carrega a malha, preserva escala, identifica defeitos e simplifica apenas a cópia de trabalho.
2. **Entendimento visual híbrido** — SegFormer trata classes humanas; CLIPSeg cria máscaras abertas a partir de texto.
3. **Projeção local** — a máscara 2D é projetada na vista atual e fornece sementes, não uma decisão final.
4. **Ensino interativo** — laços positivos e de proteção em várias vistas têm prioridade sobre os modelos.
5. **Aprendizado geométrico** — Extra Trees usa posição normalizada, normais, distância radial e curvatura diédrica.
6. **Contorno curvo** — graph cut combina custo semântico e adjacência. Dobras fortes e côncavas custam menos; arestas longas reduzem atalhos serrilhados. A sensibilidade angular é configurável.
7. **Refino** — limiar, adição/remoção, morfologia por adjacência, limpeza de componentes e desfazer.
8. **Separação e reparo** — as duas partes passam por saneamento, orientação, fechamento simples e reconstrução voxel como último recurso.
9. **Validação** — ambas precisam ser fechadas, orientadas e sem arestas abertas, não-manifold ou faces degeneradas. A validação se repete após a gravação.

O próximo salto técnico é registro de câmera por pontos de referência e consenso entre várias imagens, seguido por curvas fechadas editáveis com pontos âncora e conectores toleranciados.
