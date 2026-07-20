export interface Idea { id: string; title: string; createdAt: number; }
export function makeIdea(id: string, title: string): Idea { return { id, title, createdAt: 0 }; }
