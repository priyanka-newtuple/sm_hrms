import fs from 'node:fs/promises';
import path from 'node:path';
import ts from 'typescript';

const root = path.resolve(process.cwd(), 'src');
const targets = [
  {
    file: path.join(root, 'core/services/api.ts'),
    services: new Map([
      ['stateMachines', 'State Machines'],
      ['picklists', 'Picklists'],
      ['formSchemas', 'Form Schemas'],
      ['llmConfig', 'LLM Config'],
      ['emailConfig', 'Email Config'],
      ['transcriptionConfig', 'Transcription Config'],
      ['jobs', 'Processing Jobs'],
      ['aiFeatures', 'AI Features'],
      ['documentTypes', 'Document Types'],
      ['users', 'Users'],
      ['organizations', 'Organizations'],
      ['agent', 'Agent Definitions'],
      ['agentTraces', 'Agent Traces'],
      ['integrations', 'Integrations'],
      ['roles', 'Roles'],
      ['invitations', 'Invitations'],
    ]),
  },
  {
    file: path.join(root, 'domains/ats/services/api.ts'),
    services: new Map([
      ['funnels', 'Funnels'],
      ['playbooks', 'Playbooks'],
    ]),
  },
];

const outputFile = path.join(
  root,
  'domains/ats/settings/generated/frontendApiInventory.ts',
);

function findRequestCall(node) {
  let result = null;

  function visit(current) {
    if (result) {
      return;
    }

    if (ts.isCallExpression(current)) {
      const expressionText = current.expression.getText();
      if (expressionText === 'request' || expressionText === 'fetch') {
        result = current;
        return;
      }
    }

    current.forEachChild(visit);
  }

  visit(node);
  return result;
}

function extractPath(sourceFile, expression) {
  if (ts.isStringLiteralLike(expression)) {
    return expression.text;
  }

  if (ts.isTemplateExpression(expression)) {
    let value = expression.head.text;
    for (const span of expression.templateSpans) {
      const exprText = span.expression.getText(sourceFile);
      const nextText = span.literal.text;
      const looksLikeQueryExpression = exprText.includes('query') || exprText.includes('buildOrgQuery');
      if (!looksLikeQueryExpression) {
        value += `\${${exprText}}`;
      }
      value += nextText;
    }
    return value;
  }

  const raw = expression.getText(sourceFile).trim();
  if (raw.length >= 2) {
    const first = raw[0];
    const last = raw[raw.length - 1];
    if ((first === '\'' || first === '"' || first === '`') && first === last) {
      return raw.slice(1, -1);
    }
  }

  return null;
}

function canonicalizePath(pathValue) {
  return pathValue
    .replace(/\$\{.*\}/g, '')
    .replace(/`/g, '')
    .trim();
}

function extractMethod(options) {
  if (!options || !ts.isObjectLiteralExpression(options)) {
    return 'GET';
  }

  for (const property of options.properties) {
    if (!ts.isPropertyAssignment(property) || property.name.getText() !== 'method') {
      continue;
    }

    if (ts.isStringLiteralLike(property.initializer)) {
      return property.initializer.text.toUpperCase();
    }
  }

  return 'GET';
}

const rows = [];

for (const target of targets) {
  const source = await fs.readFile(target.file, 'utf8');
  const sourceFile = ts.createSourceFile(target.file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);

  sourceFile.forEachChild((node) => {
    if (!ts.isVariableStatement(node)) {
      return;
    }

    const isExported = node.modifiers?.some((modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword);
    if (!isExported) {
      return;
    }

    for (const declaration of node.declarationList.declarations) {
      if (!ts.isIdentifier(declaration.name)) {
        continue;
      }

      const serviceName = declaration.name.text;
      const serviceLabel = target.services.get(serviceName);
      if (!serviceLabel || !declaration.initializer || !ts.isObjectLiteralExpression(declaration.initializer)) {
        continue;
      }

      for (const property of declaration.initializer.properties) {
        if (!ts.isPropertyAssignment(property)) {
          continue;
        }

        const methodName = property.name.getText(sourceFile);
        const requestCall = findRequestCall(property.initializer);
        if (!requestCall) {
          continue;
        }

        const pathValue = requestCall.arguments[0] ? extractPath(sourceFile, requestCall.arguments[0]) : null;
        if (!pathValue || !pathValue.startsWith('/')) {
          continue;
        }

        rows.push({
          serviceGroup: serviceName,
          serviceLabel,
          methodName,
          method: extractMethod(requestCall.arguments[1]),
          path: canonicalizePath(pathValue),
          sourceFile: path.relative(root, target.file).replace(/\\/g, '/'),
        });
      }
    }
  });
}

const content = `export interface FrontendApiEndpoint {
  serviceGroup: string;
  serviceLabel: string;
  methodName: string;
  method: string;
  path: string;
  sourceFile: string;
}

export const frontendApiInventory: FrontendApiEndpoint[] = ${JSON.stringify(rows, null, 2)};
`;

await fs.writeFile(outputFile, content);
console.log(`Wrote ${rows.length} endpoints to ${outputFile}`);
