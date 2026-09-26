import { Component, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { failed: boolean };

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    const isAr = document.documentElement.dir === "rtl";
    return (
      <main className="wrap" role="alert" style={{ minHeight: "100vh", display: "grid", placeItems: "center", textAlign: "center", paddingBlock: 64 }}>
        <div className="card card-pad" style={{ maxWidth: 520 }}>
          <h1 className="display t-h2">{isAr ? "تعذر عرض الصفحة" : "The page could not load"}</h1>
          <p className="t-body" style={{ marginBlock: 14 }}>
            {isAr ? "حدث خطأ غير متوقع. أعد تحميل الصفحة للمحاولة مرة أخرى." : "Something went wrong. Reload the page to try again."}
          </p>
          <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>
            {isAr ? "إعادة التحميل" : "Reload"}
          </button>
        </div>
      </main>
    );
  }
}
