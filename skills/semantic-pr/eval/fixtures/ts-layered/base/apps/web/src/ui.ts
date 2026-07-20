import { createIdea } from "@acme/server";
export function onSubmit(title: string) { return createIdea(title); }
