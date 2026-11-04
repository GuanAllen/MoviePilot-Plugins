import federation from '@originjs/vite-plugin-federation'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [
    vue(),
    federation({
      name: 'MagicFlow',
      filename: 'remoteEntry.js',
      exposes: {
        './Page': './src/components/Page.vue',
        './Config': './src/components/Config.vue',
        './Dashboard': './src/components/Dashboard.vue',
        './AppPage': './src/components/AppPage.vue',
      },
      shared: {
        vue: {
          requiredVersion: false,
          generate: false,
          singleton: true,
        },
        vuetify: {
          requiredVersion: false,
          generate: false,
          singleton: true,
        },
        'vuetify/styles': {
          requiredVersion: false,
          generate: false,
          singleton: true,
        },
      },
      format: 'esm',
    }),
  ],
  build: {
    target: 'esnext',
    minify: false,
    cssCodeSplit: true,
  },
  css: {
    postcss: {
      plugins: [
        {
          postcssPlugin: 'internal:charset-removal',
          AtRule: {
            charset: atRule => {
              if (atRule.name === 'charset') atRule.remove()
            },
          },
        },
        {
          // ★ 只剥离「Vuetify 自带」的样式表：MoviePilot 已全局加载同一份，
          //   插件再注一份会盖掉主题变量。本插件自己的 <style> 必须保留，
          //   否则 .v-* 覆盖规则（如把 --v-medium-emphasis-opacity 抬到 0.78）会被静默删掉。
          //
          // ★ 判据补一条：带 `[data-v-xxxxxxxx]` 的一定是本插件 scoped 样式 ——
          //   Vuetify 发布出来的 CSS 里不可能出现 scope 属性限定符。
          //   少这一条，从 dist 还原成 `Xxx.js + xxx.css` 的组件（不是 .vue，走不到上面的
          //   early return）里的 `.v-icon` / `.v-btn` 覆盖规则会被整条静默删掉，
          //   表现是「样式看着少了一点点、但构建不报错、prod 也查不出来」。
          postcssPlugin: 'vuetify-filter',
          Root(root) {
            const file = (root.source && root.source.input && root.source.input.file) || ''
            if (/\.vue\b/i.test(file)) return
            root.walkRules(rule => {
              const sel = rule.selector || ''
              if (!sel.includes('.v-') && !sel.includes('.mdi-')) return
              if (/\[data-v-[0-9a-f]{8}\]/.test(sel)) return
              rule.remove()
            })
          },
        },
      ],
    },
  },
})
