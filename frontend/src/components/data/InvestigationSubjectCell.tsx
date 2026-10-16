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
        className="table-link investigation-subject-link"
        aria-label={`Open investigation ${referenceNumber}: ${formattedSubjectName}`}
        onClick={onOpen}
      >
        <span className="investigation-subject-name" title={formattedSubjectName}>
          {formattedSubjectName}
        </span>
        <span className="investigation-subject-reference" title={referenceNumber}>
          {referenceNumber}
        </span>
      </button>
    );
  }

  return (
    <div className="investigation-subject-cell">
      <span className="investigation-subject-name" title={formattedSubjectName}>
        {formattedSubjectName}
      </span>
      <span className="investigation-subject-reference" title={referenceNumber}>
        {referenceNumber}
      </span>
    </div>
  );
}
