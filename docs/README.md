# AI Invoice Processing Platform Documentation

This documentation describes an enterprise-grade AI invoice processing platform designed for forward-deployed engineering practice.

## Documents

- [Architecture Overview](architecture-overview.md)
- [System Design Explanation](system-design-explanation.md)
- [Current Implementation Status](current-implementation-status.md)
- [Docker Development](docker-development.md)
- [Implementation Roadmap](implementation-roadmap.md)
- [API Contract](api-contract.md)
- [Data Model Specification](data-model-specification.md)
- [Operational Runbook](operational-runbook.md)
- [Monitoring](monitoring.md)
- [Deployment Guide](deployment-guide.md)
- [Engineering Standards](engineering-standards.md)
- [Production Readiness Checklist](production-readiness-checklist.md)

## Diagrams

- [System Context](diagrams/system-context.mmd)
- [Invoice Processing Flow](diagrams/invoice-processing-flow.mmd)
- [Data Model](diagrams/data-model.mmd)
- [Deployment Topology](diagrams/deployment-topology.mmd)

## Target Capability

The platform allows enterprise users to upload invoice files, extract structured data using AI, validate the invoice against business rules, route exceptions to human reviewers, and maintain a complete audit trail for compliance.

## Documentation Contract

The documentation separates current implementation from target architecture:

- Current-state documents describe only what exists in the repository today.
- Target-state architecture documents describe the intended production product.
- Roadmap documents define the gap between the two and the order to close it.
- Readiness checklists are marked complete only when behavior is implemented, tested, and operationally usable.
