// DSH runtime bootstrap for the rain-tech agent worker.
//
// This module only wires public DSH services: it mounts the plugin slice the
// worker needs and bridges the LLM transport to the Python process. Business
// rules, tool side effects and receipts stay on the Python side.
import { Context } from '@deepseek-ai/cordis';
import { LlmAdapter } from '@deepseek-ai/dsh-llm';

// Order matters: later services assume the ones mounted before them exist.
const SERVICE_SEQUENCE = [
  ['session', {}],
  ['session-projection', {}],
  ['agent', {}],
  ['llm', {}],
  ['system-prompt', {}],
  ['tools', {}],
  ['agent-loop', { agents: [], maxParallelToolCalls: 1 }],
];

async function mountService(context, name, options) {
  const exported = await import(`@deepseek-ai/dsh-${name}`);
  const plugin = exported.default ?? exported;
  const config = plugin.Config ? plugin.Config(options) : options;
  const fiber = context.plugin(plugin, config);
  await fiber.inertia;
  return fiber;
}

export async function createHost() {
  const context = new Context();
  for (const [name, options] of SERVICE_SEQUENCE) {
    await mountService(context, name, options);
  }
  return context;
}

/**
 * LLM transport that forwards each request to the Python process and relays
 * the chunk stream it returns. It keeps no prompt, history or budget state.
 */
export class ModelTransportAdapter extends LlmAdapter {
  constructor(request, contextWindow = 64000) {
    super();
    this.request = request;
    this.contextWindow = contextWindow;
  }

  async resolveModel(provider, model) {
    return { provider, id: model, name: model, context: { contextWindow: this.contextWindow } };
  }

  async *stream(call) {
    const completion = await this.request(call);
    for (const chunk of completion.chunks) yield chunk;
  }
}
