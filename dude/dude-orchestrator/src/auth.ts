import { jwtVerify } from 'jose';
import { z } from 'zod';
import { DomainError } from './errors.js';

const claimsSchema = z.object({
  sub: z.uuid(), user_id: z.uuid(), username: z.string().min(1),
  role: z.enum(['user', 'admin']), iat: z.number().int(), exp: z.number().int(),
});

export async function authenticate(header: string | undefined, secret: string): Promise<string> {
  try {
    if (!header || !/^Bearer [^\s]+$/i.test(header)) throw new Error();
    const { payload } = await jwtVerify(header.slice(7), new TextEncoder().encode(secret), {
      algorithms: ['HS256'], issuer: 'alfred-admin', requiredClaims: ['sub', 'iat', 'exp'],
    });
    const claims = claimsSchema.parse(payload);
    if (claims.sub !== claims.user_id || claims.exp <= claims.iat || claims.iat > Math.floor(Date.now() / 1000) + 30) throw new Error();
    return claims.sub;
  } catch { throw new DomainError('unauthorized', 401); }
}
