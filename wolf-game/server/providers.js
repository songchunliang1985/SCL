"use strict";

function toOpenAITools(tools) {
  return tools.map(t => ({
    type: "function",
    function: { name: t.name, description: t.description, parameters: t.input_schema },
  }));
}

async function callClaude(conf, { system, user, tools, maxTokens }) {
  const body = {
    model: conf.model,
    max_tokens: maxTokens,
    system,
    messages: [{ role: "user", content: user }],
  };
  if (tools?.length) {
    body.tools = tools;
    body.tool_choice = { type: "any" };
  }
  const resp = await fetch(`${conf.baseURL}/v1/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": conf.apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`Claude API ${resp.status}: ${await resp.text()}`);
  const data = await resp.json();
  if (tools?.length) {
    const tu = (data.content || []).find(c => c.type === "tool_use");
    return { toolName: tu?.name || null, input: tu?.input || null };
  }
  const txt = (data.content || []).find(c => c.type === "text");
  return { text: txt?.text || "" };
}

async function callOpenAICompat(conf, { system, user, tools, maxTokens, extraBody }) {
  const body = {
    model: conf.model,
    messages: [
      { role: "system", content: system },
      { role: "user", content: user },
    ],
    max_tokens: maxTokens,
    temperature: 0.8,
    ...(extraBody || {}),
  };
  if (tools?.length) {
    body.tools = toOpenAITools(tools);
    body.tool_choice = "required";
  }
  const resp = await fetch(`${conf.baseURL}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${conf.apiKey}`,
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`OpenAI-compat ${resp.status}: ${await resp.text()}`);
  const data = await resp.json();
  if (tools?.length) {
    const tc = data.choices?.[0]?.message?.tool_calls?.[0];
    if (!tc) return { toolName: null, input: null };
    let input = null;
    try { input = JSON.parse(tc.function.arguments); } catch {}
    return { toolName: tc.function.name, input };
  }
  return { text: data.choices?.[0]?.message?.content || "" };
}

// DeepSeek V4 reasoner 默认开 thinking，但 thinking 模式不支持 tool_calls，
// 显式 disable 避免 400 "does not support this tool_choice"
const REGISTRY = {
  claude:   { call: (conf, opts) => callClaude(conf, opts) },
  openai:   { call: (conf, opts) => callOpenAICompat(conf, opts) },
  deepseek: { call: (conf, opts) => callOpenAICompat(conf, { ...opts, extraBody: { thinking: { type: "disabled" } } }) },
};

async function dispatch(providerName, providerConf, opts) {
  const provider = REGISTRY[providerName];
  if (!provider) throw new Error(`unknown provider: ${providerName}`);
  return provider.call(providerConf, opts);
}

module.exports = { dispatch, REGISTRY };
