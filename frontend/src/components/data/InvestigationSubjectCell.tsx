import { formatUserName } from "../../utils/userName";

type InvestigationSubjectCellProps = {
  subjectName: string;
  referenceNumber: string;
  onOpen?: () => void;
};

export function InvestigationSubjectCell({
  subjectName,
  referenceNumber,
  onOpen,
}: InvestigationSubjectCellProps) {
  const formattedSubjectName = formatUserName(subjectName);
  if (onOpen) {
    return (
      <button
        type="button"
        className="table-link investigation-subject-link grid min-w-0 gap-1 text-left"
        aria-label={`Open investigation ${referenceNumber}: ${formattedSubjectName}`}
        onClick={onOpen}
      >
        <span className="investigation-subject-name block truncate text-[13px] font-semibold text-[#1d3558]" title={formattedSubjectName}>
          {formattedSubjectName}
        </span>
        <span className="investigation-subject-reference block truncate font-mono text-[11px] text-[#71829c]" title={referenceNumber}>
          {referenceNumber}
        </span>
      </button>
    );
  }

  return (
    <div className="investigation-subject-cell grid min-w-0 gap-1">
      <span className="investigation-subject-name block truncate text-[13px] font-semibold text-[#1d3558]" title={formattedSubjectName}>
        {formattedSubjectName}
      </span>
      <span className="investigation-subject-reference block truncate font-mono text-[11px] text-[#71829c]" title={referenceNumber}>
        {referenceNumber}
      </span>
    </div>
  );
}
