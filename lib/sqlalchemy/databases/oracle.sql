create or replace package sqlalchemy
is
        function is_not(operand number)
                return number deterministic;

        function is_and(left number, right number)
                return number deterministic;

        function is_or(left number, right number)
                return number deterministic;



        function is_is_null(left char)
                return number deterministic;

        function is_is_null(left number)
                return number deterministic;

        function is_is_null(left date)
                return number deterministic;

        function is_is_not_null(left char)
                return number deterministic;

        function is_is_not_null(left number)
                return number deterministic;

        function is_is_not_null(left date)
                return number deterministic;

        function is_equal(left char, right char)
                return number deterministic;

        function is_equal(left number, right number)
                return number deterministic;

        function is_equal(left date, right date)
                return number deterministic;

        function is_not_equal(left char, right char)
                return number deterministic;

        function is_not_equal(left number, right number)
                return number deterministic;

        function is_not_equal(left date, right date)
                return number deterministic;

        function is_greater(left char, right char)
                return number deterministic;

        function is_greater(left number, right number)
                return number deterministic;

        function is_greater(left date, right date)
                return number deterministic;

        function is_smaller(left char, right char)
                return number deterministic;

        function is_smaller(left number, right number)
                return number deterministic;

        function is_smaller(left date, right date)
                return number deterministic;

        function is_greater_or_equal(left char, right char)
                return number deterministic;

        function is_greater_or_equal(left number, right number)
                return number deterministic;

        function is_greater_or_equal(left date, right date)
                return number deterministic;

        function is_smaller_or_equal(left char, right char)
                return number deterministic;

        function is_smaller_or_equal(left number, right number)
                return number deterministic;

        function is_smaller_or_equal(left date, right date)
                return number deterministic;

end sqlalchemy;
/

show errors;

/**
 * SQLAlchemy PL/SQL functions for supporting functionality such
 * as boolean selects.
 */
create or replace package body sqlalchemy
is
        function is_not(operand number)
                return number deterministic
        is
        begin
                if operand != 0 then
                        return 0;
                else
                        return 1;
                end if;
                return 1 - operand;
        end;

        function is_and(left number, right number)
                return number deterministic
        is
        begin
                return left * right;
        end;

        function is_or(left number, right number)
                return number deterministic
        is
        begin
                return left + right;
        end;



        function is_is_null(left char)
                return number deterministic
        is
        begin
                if left is null then
                        return 1;
                end if;

                return 0;
        end;

        function is_is_null(left number)
                return number deterministic
        is
        begin
                if left is null then
                        return 1;
                end if;

                return 0;
        end;

        function is_is_null(left date)
                return number deterministic
        is
        begin
                if left is null then
                        return 1;
                end if;

                return 0;
        end;

        function is_is_not_null(left char)
                return number deterministic
        is
        begin
                if left is not null then
                        return 1;
                end if;

                return 0;
        end;

        function is_is_not_null(left number)
                return number deterministic
        is
        begin
                if left is not null then
                        return 1;
                end if;

                return 0;
        end;

        function is_is_not_null(left date)
                return number deterministic
        is
        begin
                if left is not null then
                        return 1;
                end if;

                return 0;
        end;

        function is_equal(left char, right char)
                return number deterministic
        is
        begin
                if left = right then
                        return 1;
                end if;

                return 0;
        end;

        function is_equal(left number, right number)
                return number deterministic
        is
        begin
                if left = right then
                        return 1;
                end if;

                return 0;
        end;

        function is_equal(left date, right date)
                return number deterministic
        is
        begin
                if left = right then
                        return 1;
                end if;

                return 0;
        end;

        function is_not_equal(left char, right char)
                return number deterministic
        is
        begin
                if left != right then
                        return 1;
                end if;

                return 0;
        end;

        function is_not_equal(left number, right number)
                return number deterministic
        is
        begin
                if left != right then
                        return 1;
                end if;

                return 0;
        end;

        function is_not_equal(left date, right date)
                return number deterministic
        is
        begin
                if left != right then
                        return 1;
                end if;

                return 0;
        end;

        function is_greater(left char, right char)
                return number deterministic
        is
        begin
                if left > right then
                        return 1;
                end if;

                return 0;
        end;

        function is_greater(left number, right number)
                return number deterministic
        is
        begin
                if left > right then
                        return 1;
                end if;

                return 0;
        end;

        function is_greater(left date, right date)
                return number deterministic
        is
        begin
                if left > right then
                        return 1;
                end if;

                return 0;
        end;

        function is_smaller(left char, right char)
                return number deterministic
        is
        begin
                if left < right then
                        return 1;
                end if;

                return 0;
        end;

        function is_smaller(left number, right number)
                return number deterministic
        is
        begin
                if left < right then
                        return 1;
                end if;

                return 0;
        end;

        function is_smaller(left date, right date)
                return number deterministic
        is
        begin
                if left < right then
                        return 1;
                end if;

                return 0;
        end;

        function is_greater_or_equal(left char, right char)
                return number deterministic
        is
        begin
                if left >= right then
                        return 1;
                end if;

                return 0;
        end;

        function is_greater_or_equal(left number, right number)
                return number deterministic
        is
        begin
                if left >= right then
                        return 1;
                end if;

                return 0;
        end;

        function is_greater_or_equal(left date, right date)
                return number deterministic
        is
        begin
                if left >= right then
                        return 1;
                end if;

                return 0;
        end;

        function is_smaller_or_equal(left char, right char)
                return number deterministic
        is
        begin
                if left <= right then
                        return 1;
                end if;

                return 0;
        end;

        function is_smaller_or_equal(left number, right number)
                return number deterministic
        is
        begin
                if left <= right then
                        return 1;
                end if;

                return 0;
        end;

        function is_smaller_or_equal(left date, right date)
                return number deterministic
        is
        begin
                if left <= right then
                        return 1;
                end if;

                return 0;
        end;

end sqlalchemy;
/

show errors;