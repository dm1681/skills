export interface Idea { id: string; title: string; }
export function makeIdea(id: string, title: string): Idea { return { id, title }; }
