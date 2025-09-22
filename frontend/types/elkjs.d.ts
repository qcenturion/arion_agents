declare module "elkjs/lib/elk.bundled.js" {
  export default class ELK {
    constructor(options?: Record<string, unknown>);
    layout(graph: Record<string, unknown>): Promise<any>;
  }
}
