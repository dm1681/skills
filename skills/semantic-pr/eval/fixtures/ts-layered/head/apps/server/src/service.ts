import { Idea, makeIdea } from "@acme/contracts";
export function createIdea(title: string): Idea { return makeIdea("gen", title.trim()); }
