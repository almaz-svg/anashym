// Audit source literals and interpolation placeholders without translating business data.
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../frontend/node_modules/typescript');
async function main() {
  const root = path.resolve(__dirname, '../frontend/src');
  const built = ts.transpileModule(fs.readFileSync(path.join(root, 'translations.ts'), 'utf8'), {compilerOptions: {module:ts.ModuleKind.ESNext, target:ts.ScriptTarget.ES2022}});
  const {translations} = await import('data:text/javascript;base64,' + Buffer.from(built.outputText).toString('base64'));
  const missing = [], rawJsx = [], placeholders = [];
  const fixedLanguageNames = new Set(['Русский', 'Қазақша', 'ҚАЗ']);
  const knownStoredValues = new Set(['Отмена клиентом']);
  for (const name of fs.readdirSync(root).filter(name => /\.tsx?$/.test(name) && !/test|translations/.test(name))) {
    const text = fs.readFileSync(path.join(root,name),'utf8');
    const tree = ts.createSourceFile(name,text,ts.ScriptTarget.Latest,true,name.endsWith('tsx')?ts.ScriptKind.TSX:ts.ScriptKind.TS);
    function walk(node) {
      if (ts.isStringLiteral(node) && /[А-Яа-яЁё]/.test(node.text) && !fixedLanguageNames.has(node.text) && !knownStoredValues.has(node.text) && !translations[node.text]) {
        missing.push({file:name,line:tree.getLineAndCharacterOfPosition(node.getStart(tree)).line+1,text:node.text});
      }
      if (ts.isJsxText(node) && /[А-Яа-яЁё]/.test(node.text) && !fixedLanguageNames.has(node.text.trim())) rawJsx.push({file:name,text:node.text.trim()});
      ts.forEachChild(node,walk);
    }
    walk(tree);
  }
  const tokens = s => [...s.matchAll(/\{\{(\w+)\}\}/g)].map(x=>x[1]).sort().join(',');
  for (const [key, values] of Object.entries(translations)) for (const language of ['en','kk']) if (!values[language] || tokens(key)!==tokens(values[language])) placeholders.push({key,language});
  const result = {keys:Object.keys(translations).length,missing,rawJsx,placeholders};
  fs.writeFileSync(path.join(__dirname,'localization-audit.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result,null,2));
  process.exitCode = missing.length || rawJsx.length || placeholders.length ? 1 : 0;
}
main().catch(e=>{console.error(e);process.exitCode=1});
