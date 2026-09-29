# Padrão visual do frontend

O frontend do Billing Control utiliza uma identidade roxo, rosa, branco e cinza-claro. Os tokens oficiais estão centralizados no início da seção `Billing Control visual system` em `frontend/web/app/extended.css`.

## Tokens principais

- Primary: `#7B2FF2`
- Secondary: `#F357A8`
- Background: `#F8F9FA`
- Surface: `#FFFFFF`
- Text dark: `#495057`
- Text secondary: `#6C757D`
- Border: `#DEE2E6`
- Success: `#28A745`
- Danger: `#DC3545`
- Warning: `#FFC107`
- Info: `#17A2B8`

Botões primários usam gradiente horizontal roxo–rosa. A sidebar usa o mesmo gradiente na vertical.

## Estrutura das telas

Telas autenticadas seguem: sidebar, topbar, título e ação principal, card de conteúdo e footer. A sidebar tem 220 px, fica compacta em 60 px até 900 px e desaparece até 600 px.

Cards usam superfície branca, raio de 18 px e sombra `0 2px 16px rgba(123, 47, 242, 0.08)`. Controles usam raio de 8 px.

## Clínica ativa

O seletor permanece na sidebar. Trocar o valor atualiza o contexto do frontend, mas toda requisição continua enviando explicitamente o identificador da clínica para validação no backend.

## Odontograma

Os estilos-base de dentes e dos estados saudável, cárie, restauração, canal e extraído já fazem parte do tema. A implementação funcional do odontograma continua fora do MVP atual.
