import { useEffect, useState } from "react";

const DOCS: [string, string][] = [
  ["README", "README"],
  ["Architecture", "ARCHITECTURE"],
  ["Scientific Models", "SCIENTIFIC_MODELS"],
  ["Quantum Information", "QUANTUM_INFORMATION"],
  ["Network Models", "NETWORK_MODELS"],
  ["QEC Models", "QEC_MODELS"],
  ["Hardware Models", "HARDWARE_MODELS"],
  ["Mitigation Models", "MITIGATION_MODELS"],
  ["Experiments", "EXPERIMENTS"],
  ["Limitations", "LIMITATIONS"],
  ["Testing", "TESTING"],
  ["Roadmap", "ROADMAP"],
  ["Decisions", "ARCHITECTURE_DECISIONS"],
  ["Session Log", "AUTONOMOUS_SESSION_LOG"],
  ["Final Report", "AUTONOMOUS_FINAL_REPORT"],
];

export default function DocsPage() {
  const [active, setActive] = useState(DOCS[0][1]);
  const [content, setContent] = useState<string>("");

  useEffect(() => {
    fetch(`/docs-files/${active}.md`)
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error("not served"))))
      .then(setContent)
      .catch(() =>
        setContent(
          `# ${active}\n\nThis documentation file lives in the repository at docs/${active}.md.\n` +
          "Serve the docs directory with the frontend dev server to view it here,\n" +
          "or read the file directly in the repository."
        )
      );
  }, [active]);

  return (
    <div>
      <h1 className="page-title">Documentation</h1>
      <p className="page-sub">
        Scientific assumptions, formulas, and limitations are documented alongside the
        implementation. Documentation that contradicts the code is treated as a defect.
      </p>
      <div className="row" style={{ marginBottom: 12 }}>
        {DOCS.map(([label, file]) => (
          <button key={file} className={"btn small " + (active === file ? "" : "secondary")}
                  onClick={() => setActive(file)}>
            {label}
          </button>
        ))}
      </div>
      <div className="panel">
        <pre style={{ whiteSpace: "pre-wrap", fontSize: 13, lineHeight: 1.55 }}>{content}</pre>
      </div>
    </div>
  );
}
