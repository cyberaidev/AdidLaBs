// Centralized copy deck — all user-facing strings live here (design.md §6).
// Concept demo — no affiliation with adidas AG. All products fictional.

export const COPY = {
  brand: { name: "AdidLaBs" },

  utility: {
    left: "FREE SHIPPING ON THE FORECAST",
    right: ["HELP", "RETURNS", "AU $"],
  },

  nav: ["SHOES", "MEN", "WOMEN", "KIDS", "WEATHER LAB", "OUTLET"],
  navRedItem: "OUTLET",

  hero: {
    line1: "ADIDLABS",
    line2: "FORECAST COLLECTION",
    labelBoxes: ["NEW", "AI STYLED", "3-DAY FORECAST"],
    cta: "SHOP NOW",
    ctaArrow: "→",
    // Right-hand 2×2 weather-conditions photo panel (banner mockup 2026-07-22).
    // Unsplash photos (Unsplash License — free to use, no branded goods shown).
    media: [
      {
        src: "https://images.unsplash.com/photo-1601297183305-6df142704ea2?auto=format&fit=crop&w=800&q=80",
        alt: "Sunny day — clear blue sky",
        temp: "28°",
        label: "SUNNY",
      },
      {
        src: "https://images.unsplash.com/photo-1428592953211-077101b2021b?auto=format&fit=crop&w=800&q=80",
        alt: "Raining — heavy rain on window",
        temp: "14°",
        label: "RAINING",
      },
      {
        src: "https://images.unsplash.com/photo-1418985991508-e47386d96a71?auto=format&fit=crop&w=800&q=80",
        alt: "Snow — snowfall in the forest",
        temp: "2°",
        label: "SNOW",
      },
      {
        src: "https://images.unsplash.com/photo-1505672678657-cc7037095e60?auto=format&fit=crop&w=800&q=80",
        alt: "Windy — trees bending in strong wind",
        temp: "16°",
        label: "WINDY",
      },
    ],
  },

  weatherBar: {
    lockedText: "WEATHER LAB LOCKED — JOIN THE LAB TO SEE YOUR 3-DAY FORECAST",
  },

  rail: {
    heading: "PICKED FOR YOUR FORECAST",
    sub: "Weather-matched by the stylist agents.",
    addToBag: "ADD TO BAG",
    browseLabel: "BROWSE THE FULL CATALOG:",
  },

  agentsPanel: {
    heading: "AGENTS ON BEDROCK AGENTCORE",
    sub: "Live roster · region ap-southeast-2 (Sydney).",
    statusRunning: "RUNNING",
    statusStandby: "STANDBY",
  },

  gate: {
    title: "JOIN THE LAB",
    sub: "Register to unlock your weather-matched stylist.",
    fields: { name: "NAME", email: "EMAIL", password: "PASSWORD" },
    primary: "CREATE LAB ACCOUNT",
    secondary: "Already in the lab? Log in",
  },

  login: {
    title: "LOG IN",
    fields: { email: "EMAIL", password: "PASSWORD" },
    primary: "ENTER THE LAB",
    secondary: "Need an account? Join the lab",
  },

  chat: {
    title: "STYLIST",
    seed: "Reading your 3-day forecast…",
    placeholder: "Ask the stylist…",
    send: "SEND",
    // Sent automatically once per session to pre-fill the bag (AI CHOICE rows).
    autoKitPrompt:
      "Build me a weather-matched starter kit for the next 3 days — one pick per relevant category.",
  },

  architecture: {
    title: "ARCHITECTURE",
    region: "ap-southeast-2 (Sydney)",
    githubDocUrl:
      "https://github.com/cyberaidev/AdidLaBs/blob/main/docs/architecture.md",
    layers: [
      "CloudFront + S3 — static React SPA (private bucket, OAC)",
      "API Gateway HTTP API — JWT authorizer → Cognito",
      "Lambda api-handler — Python 3.12",
      "DynamoDB — adidlabs-catalog, adidlabs-bag (PAY_PER_REQUEST)",
      "Bedrock AgentCore Runtime — LangGraph orchestrator + 7 agents",
      "AgentCore Gateway — MCP tool surface",
      "LiteLLM on Lambda — aws-lambda-web-adapter, IAM-auth function URL",
      "Bedrock Knowledge Bases over Amazon S3 Vectors — Titan Text v2 (FAISS-in-Lambda fallback)",
    ],
  },

  bag: {
    title: "BAG",
    subtotal: "SUBTOTAL",
    checkout: "CHECKOUT (DEMO)",
    empty: "Your bag is empty.",
    aiNote:
      "Items tagged AI CHOICE were matched to your forecast by the stylist mesh — keep them, remove them, or add your own.",
  },

  litellm: {
    heading: "LITELLM GATEWAY",
    sub: "Model telemetry via Bedrock",
    empty: "No model traffic in this window yet — chat with the stylist to generate some.",
    foot: "Live CloudWatch AWS/Bedrock metrics · routes nova-pro + haiku-4.5 (APAC inference profiles) + Titan embeddings (KB) · refreshes every 60s (CloudWatch aggregates lag a few minutes).",
  },
  wishlist: {
    title: "WISHLIST",
    moveToBag: "MOVE TO BAG",
    empty: "No saved items yet.",
  },

  footer: {
    columns: {
      SHOP: ["Shoes", "Pants", "Tshirt", "Jumper", "Jacket", "Accessory"],
      LAB: ["Weather Lab", "Forecast Collection", "Deals"],
      HELP: ["Shipping", "Returns", "Sizing"],
      ABOUT: ["Concept", "Tech", "GitHub"],
    },
    // Real destinations for footer entries; anything not listed here renders
    // as a decorative dead link (the demo has no such pages).
    columnLinks: {
      GitHub: "https://github.com/cyberaidev/AdidLaBs",
      Tech: "https://github.com/cyberaidev/AdidLaBs/blob/main/docs/architecture.md",
    },
    repoUrl: "https://github.com/cyberaidev/AdidLaBs",
    repoLabel: "github.com/cyberaidev/AdidLaBs",
    buildLine: "Built on AWS Bedrock AgentCore · ap-southeast-2 (Sydney)",
    disclaimer:
      "Concept demo — no affiliation with adidas AG. All products fictional.",
    license: "MIT © cyberaidev ·",
    dataAttribution:
      "Mock data: HuggingFace ashraq/fashion-product-images-small (metadata only), synthetic prices.",
  },

  // Static roster — rendered verbatim, and used as the fallback when GET /api/agents is unreachable.
  agents: [
    { name: "ORCHESTRATOR", wid: "adidlabs/orchestrator-9f21", route: "NOVA-PRO" },
    { name: "WEATHER", wid: "adidlabs/weather-3b7c", route: "HAIKU-4.5" },
    { name: "SHOES", wid: "adidlabs/shoes-4e2a", route: "HAIKU-4.5" },
    { name: "PANTS", wid: "adidlabs/pants-8c1d", route: "HAIKU-4.5" },
    { name: "TSHIRT", wid: "adidlabs/tshirt-2a9e", route: "HAIKU-4.5" },
    { name: "JUMPER", wid: "adidlabs/jumper-6d3f", route: "HAIKU-4.5" },
    { name: "JACKET", wid: "adidlabs/jacket-1e8b", route: "HAIKU-4.5" },
    { name: "ACCESSORY", wid: "adidlabs/accessory-5c4a", route: "HAIKU-4.5" },
  ],
};
