import { Link } from "react-router-dom";
import { ShieldOff, SearchX } from "lucide-react";

function Shell({ icon: Icon, title, message }) {
  return (
    <div className="grid min-h-[60vh] place-items-center px-4">
      <div className="text-center">
        <Icon className="mx-auto h-8 w-8 text-ink-300" />
        <h1 className="mt-3 text-lg font-semibold text-ink-900">{title}</h1>
        <p className="mt-1 max-w-sm text-sm text-ink-500">{message}</p>
        <Link to="/" className="btn-primary mt-5">
          Back to dashboard
        </Link>
      </div>
    </div>
  );
}

export function Forbidden() {
  return (
    <Shell
      icon={ShieldOff}
      title="You do not have access to this"
      message="Your role does not hold the permission this page needs. The same check runs on the server, so nothing was exposed."
    />
  );
}

export function NotFound() {
  return (
    <Shell
      icon={SearchX}
      title="Page not found"
      message="That address does not match anything in the application."
    />
  );
}
