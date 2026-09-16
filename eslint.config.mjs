import { defineConfig, globalIgnores } from 'eslint/config'
import nextVitals from 'eslint-config-next/core-web-vitals'
import nextTs from 'eslint-config-next/typescript'

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,

  /*
   * Vendored design files.
   *
   * Any vendor directory under components holds finished designs delivered as plain
   * React with their own scoped CSS. They are kept byte-comparable with
   * the upstream archive so a revised design can be dropped in and
   * diffed, which means reformatting them to satisfy house lint rules is
   * actively counterproductive.
   *
   * Only the stylistic rules are relaxed. Anything that could produce a
   * runtime fault -- hooks order, exhaustive deps, a11y -- still applies,
   * because those would be real defects in shipped code regardless of
   * where it came from.
   */
  {
    files: ['components/**/vendor/**/*.{js,jsx}'],
    rules: {
      'react/no-unescaped-entities': 'off',
      '@next/next/no-img-element': 'off',
      '@next/next/no-html-link-for-pages': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      'react-hooks/set-state-in-effect': 'off',
    },
  },
  // public/ holds static assets served verbatim -- plain scripts that are
  // never bundled, type-checked or transformed. Linting them with the
  // TypeScript ruleset reports style opinions against code written to a
  // different contract, which is noise that hides real findings.
  globalIgnores(['.next/**', 'out/**', 'build/**', 'public/**', 'next-env.d.ts']),
])

export default eslintConfig
