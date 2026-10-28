import { z } from 'zod';

export const fieldSchema = z.object({
  value: z.string().max(12000),
  source: z.enum(['user_stated', 'defaulted', 'agent_suggested', 'unresolved']),
  reason: z.string().max(2000).optional(),
}).strict();

export const briefSchema = z.object({
  schema_version: z.literal(1),
  idea: fieldSchema,
  demo_action: fieldSchema,
  demo_result: fieldSchema,
  scope: fieldSchema,
  constraints: fieldSchema,
  platform: fieldSchema,
  technology: fieldSchema,
  data: fieldSchema,
  privacy: fieldSchema,
}).strict();

export type Brief = z.infer<typeof briefSchema>;

export function emptyBrief(): Brief {
  const unknown = () => ({ value: '', source: 'unresolved' as const });
  return {
    schema_version: 1, idea: unknown(), demo_action: unknown(), demo_result: unknown(),
    scope: unknown(), constraints: unknown(), platform: unknown(), technology: unknown(),
    data: unknown(), privacy: unknown(),
  };
}

export function canGenerate(brief: Brief): boolean {
  return [brief.demo_action, brief.demo_result].every(field =>
    field.value.trim().length > 0 && ['user_stated', 'defaulted'].includes(field.source));
}

export const wikiSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('published'), version: z.string().trim().min(1).max(200) }).strict(),
  z.object({ kind: z.literal('seed'), version: z.string().trim().min(1).max(200) }).strict(),
  z.object({ kind: z.literal('none') }).strict(),
]);
export type WikiReference = z.infer<typeof wikiSchema>;
