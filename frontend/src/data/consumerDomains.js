// Consumer mailbox providers rejected at registration. The Cognito PreSignUp
// trigger enforces the same list server-side (infra/template.yaml) — this
// client-side copy only exists for instant, friendlier validation UX.
export const CONSUMER_DOMAINS = new Set([
  "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "yahoo.co.in",
  "yahoo.fr", "yahoo.de", "ymail.com", "rocketmail.com", "hotmail.com",
  "hotmail.co.uk", "hotmail.fr", "hotmail.it", "outlook.com", "outlook.jp",
  "live.com", "msn.com", "icloud.com", "me.com", "mac.com", "aol.com",
  "proton.me", "protonmail.com", "pm.me", "gmx.com", "gmx.net", "gmx.de",
  "mail.com", "mail.ru", "yandex.com", "yandex.ru", "zoho.com", "qq.com",
  "163.com", "126.com", "naver.com", "daum.net", "rediffmail.com",
  "tutanota.com", "tuta.io", "hey.com", "fastmail.com", "inbox.com",
  "libero.it", "web.de", "seznam.cz", "wp.pl", "o2.pl", "laposte.net",
  "orange.fr", "free.fr",
]);

export function isConsumerEmail(email) {
  const domain = String(email || "").trim().toLowerCase().split("@").pop();
  return CONSUMER_DOMAINS.has(domain);
}
