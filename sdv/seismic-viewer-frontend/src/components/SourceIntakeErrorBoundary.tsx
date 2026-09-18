import React from "react";

type Props = {
  children: React.ReactNode;
  resetKey?: string;
};

type State = {
  hasError: boolean;
  message: string;
};

export default class SourceIntakeErrorBoundary extends React.Component<Props, State> {
  state: State = {
    hasError: false,
    message: "",
  };

  static getDerivedStateFromError(error: unknown): State {
    return {
      hasError: true,
      message: error instanceof Error ? error.message : "Source Intake panel failed to render.",
    };
  }

  componentDidUpdate(prevProps: Props) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({
        hasError: false,
        message: "",
      });
    }
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <section
        style={{
          marginTop: 16,
          border: "1px solid #7f1d1d",
          borderRadius: 10,
          background: "rgba(127,29,29,.18)",
          padding: 14,
          color: "#fecaca",
        }}
      >
        <h3 style={{ margin: 0, fontSize: 16 }}>Source Intake panel failed to render</h3>
        <div style={{ marginTop: 6, fontSize: 12, whiteSpace: "pre-wrap" }}>
          {this.state.message}
        </div>
        <div style={{ marginTop: 8, fontSize: 12, color: "#fca5a5" }}>
          The rest of Data Manager is protected. Select another source or refresh after the load-sheet payload is inspected.
        </div>
      </section>
    );
  }
}
