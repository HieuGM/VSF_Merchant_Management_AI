/**
 * Restaurant result card — one candidate from the agent (or Explore search).
 * fe2 reference layout: circular real food photo (fallback cuisine icon) on the left
 * with a rank badge overlapping, name/cuisine/rating/distance body, and a solid green
 * MATCH badge on the right. Interactive: click to expand address + copy.
 */
import { useState } from "react";
import type { CSSProperties, KeyboardEvent, MouseEvent } from "react";
import {
  CakeSlice,
  Check,
  Coffee,
  Copy,
  Croissant,
  Drumstick,
  Egg,
  Fish,
  IceCreamCone,
  MapPin,
  Pizza,
  Salad,
  Soup,
  Utensils,
  Wine,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { StarRating } from "./star-rating";
import type { RestaurantResult } from "../api/customer-agent-client";
import "./restaurant-card.css";

/** Keyword → icon. Order matters: more specific first. Used as the photo fallback. */
const CUISINE_ICON: Array<[RegExp, LucideIcon]> = [
  [/cà phê|cafe|coffee|trà sữa|milk ?tea|trà đạo|tea/i, Coffee],
  [/pizza/i, Pizza],
  [/sushi|hải sản|seafood|cá|fish|ốc/i, Fish],
  [/kem|ice ?cream/i, IceCreamCone],
  [/bánh kem|cake|dessert|ngọt|sweet|chè/i, CakeSlice],
  [/bánh mì|bakery|croissant|tiệm bánh/i, Croissant],
  [/rượu|wine|vang|beer|bia|pub|nhậu/i, Wine],
  [/chay|vegan|vegetarian|rau|salad/i, Salad],
  [/gà|chicken|vịt|duck|nướng|grill|bbq|quay/i, Drumstick],
  [/trứng|egg/i, Egg],
  [/phở|pho|bún|bun|mì|mi|noodle|soup|hủ tiếu|hu tieu|miến/i, Soup],
  [/cơm|rice|món việt|việt nam|quán ăn/i, Utensils],
];

function iconFor(cuisine?: string | null, name?: string | null): LucideIcon {
  const text = `${cuisine ?? ""} ${name ?? ""}`.toLowerCase();
  for (const [re, Icon] of CUISINE_ICON) if (re.test(text)) return Icon;
  return Utensils;
}

export function RestaurantCard({ item, rank }: { item: RestaurantResult; rank?: number }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [imgFailed, setImgFailed] = useState(false);
  const match = item.match_score != null ? Math.round(item.match_score * 100) : null;
  const Icon = iconFor(item.cuisine, item.name);
  const showRank = rank != null && rank > 0 && rank <= 3;
  const showPhoto = !!item.image_url && !imgFailed;

  const toggle = () => setExpanded((v) => !v);
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      toggle();
    }
  };
  const copy = async (e: MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(item.address ?? item.name);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard blocked — ignore */
    }
  };

  return (
    <article
      className={`rcard cust-card ${expanded ? "is-expanded" : ""}`}
      role="button"
      tabIndex={0}
      aria-expanded={expanded}
      aria-label={`${item.name}${item.cuisine ? `, ${item.cuisine}` : ""}`}
      onClick={toggle}
      onKeyDown={onKeyDown}
    >
      <div className="rcard__main">
        <span className={`rcard__media ${showPhoto ? "has-photo" : ""}`} aria-hidden="true">
          {showPhoto ? (
            <img
              className="rcard__img"
              src={item.image_url as string}
              alt=""
              loading="lazy"
              onError={() => setImgFailed(true)}
            />
          ) : (
            <span className="rcard__icon">
              <Icon size={22} strokeWidth={2} />
            </span>
          )}
          {showRank && <span className="rcard__rank">#{rank}</span>}
        </span>

        <div className="rcard__body">
          <h3 className="rcard__name">{item.name}</h3>
          <div className="rcard__stats">
            {item.cuisine && <span className="rcard__cuisine">{item.cuisine}</span>}
            {item.avg_rating != null && (
              <span className="rcard__stat">
                <StarRating value={item.avg_rating} size={13} />
                <b>{item.avg_rating.toFixed(1)}</b>
              </span>
            )}
            {item.distance_km != null && (
              <span className="rcard__stat rcard__stat--muted">
                <MapPin size={13} /> {item.distance_km.toFixed(1)} km
              </span>
            )}
          </div>
        </div>

        {match != null && (
          <div
            className="rcard__match"
            style={{ "--pct": match } as CSSProperties}
            title={`Độ phù hợp ${match}%`}
            aria-hidden="true"
          >
            <span className="rcard__match-num">{match}</span>
            <span className="rcard__match-lbl">match</span>
          </div>
        )}
      </div>

      {expanded && (
        <div className="rcard__detail">
          {item.address && (
            <p className="rcard__address">
              <MapPin size={14} /> {item.address}
            </p>
          )}
          <button type="button" className="rcard__copy" onClick={copy}>
            {copied ? (
              <>
                <Check size={14} /> Đã sao chép
              </>
            ) : (
              <>
                <Copy size={14} /> Sao chép địa chỉ
              </>
            )}
          </button>
        </div>
      )}
    </article>
  );
}
