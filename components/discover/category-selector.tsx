"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { AT_CATEGORIES } from "@/lib/types";
import type { ATCategory } from "@/lib/types";

interface CategorySelectorProps {
  selectedCategories: ATCategory[];
  onCategoryToggle: (category: ATCategory) => void;
  onSelectAll: () => void;
  onClearAll: () => void;
  disabled?: boolean;
}

export function CategorySelector({
  selectedCategories,
  onCategoryToggle,
  onSelectAll,
  onClearAll,
  disabled = false,
}: CategorySelectorProps) {
  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-foreground">Select Categories</CardTitle>
            <CardDescription className="text-muted-foreground">
              Choose which AT categories to search for new tools
            </CardDescription>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={onSelectAll}
              disabled={disabled}
              className="border-border text-muted-foreground hover:bg-secondary hover:text-foreground"
            >
              Select All
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={onClearAll}
              disabled={disabled}
              className="border-border text-muted-foreground hover:bg-secondary hover:text-foreground"
            >
              Clear
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {AT_CATEGORIES.map((category) => (
            <div key={category} className="flex items-start gap-3">
              <Checkbox
                id={category}
                checked={selectedCategories.includes(category)}
                onCheckedChange={() => onCategoryToggle(category)}
                disabled={disabled}
                className="mt-0.5 border-border data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground"
              />
              <Label
                htmlFor={category}
                className="text-sm leading-tight text-foreground cursor-pointer"
              >
                {category}
              </Label>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
