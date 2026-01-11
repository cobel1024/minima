lua << EOF
require("mason-lspconfig").setup({
  automatic_enable = {
    "ty",
  }
})
EOF
